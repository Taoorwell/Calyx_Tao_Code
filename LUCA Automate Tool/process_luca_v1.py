import os
import time
import argparse
import pyperclip
import geopandas as gpd
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

def convert_shapefile_to_geojson(shapefile_path, tolerance):
    print("\n📄 Converting shapefile to GeoJSON...")
    gdf = gpd.read_file(shapefile_path)

    # Remove Z values if present
    def drop_z(geom):
        if geom is None:
            return None
        if geom.has_z:
            # Rebuild geometry without Z values
            geom_type = geom.geom_type
            if geom_type == 'Point':
                x, y = geom.coords[0][:2]
                return type(geom)((x, y))
            elif geom_type in ['LineString', 'LinearRing']:
                return type(geom)([(x, y) for x, y, *_ in geom.coords])
            elif geom_type == 'Polygon':
                shell = [(x, y) for x, y, *_ in geom.exterior.coords]
                holes = [
                    [(x, y) for x, y, *_ in hole.coords]
                    for hole in geom.interiors
                ]
                return type(geom)(shell, holes)
            elif geom_type.startswith('Multi') or geom_type == 'GeometryCollection':
                return type(geom)([drop_z(part) for part in geom.geoms])
        return geom

    gdf["geometry"] = gdf["geometry"].apply(drop_z)

    # Convert to WGS84 (EPSG:4326)
    if gdf.crs != "EPSG:4326":
        print(f"🌍 Converting CRS from {gdf.crs} to WGS84 (EPSG:4326)...")
        gdf = gdf.to_crs(epsg=4326)

    # Simplify geometries
    print(f"🧹 Simplifying geometries with tolerance={tolerance}...")
    gdf["geometry"] = gdf["geometry"].simplify(
        tolerance=tolerance, preserve_topology=True
    )

    # Save to GeoJSON
    geojson_path = shapefile_path.with_suffix(".geojson")
    gdf.to_file(geojson_path, driver='GeoJSON')
    print(f"✅ GeoJSON file saved at: {geojson_path}")
    return geojson_path


def setup_browser(download_dir):
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--enable-javascript")
    options.add_argument("--log-level=3")  # Suppress most logs (INFO, WARNING)
    options.add_experimental_option("excludeSwitches", ["enable-logging"])  # Suppress DevTools logs
    options.add_experimental_option("prefs", {
        "download.default_directory": str(download_dir),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    })
    return webdriver.Chrome(options=options)


def process_geojson_file(driver, geojson_path, download_dir):
    print(f"\n📄 Processing: {geojson_path.name}")
    with open(geojson_path, 'r', encoding='utf-8') as f:
        geojson_text = f.read()

    driver.get("https://global-forest-structure.projects.earthengine.app/view/luca-viewer")
    print("Loading LUCA site...")
    time.sleep(5)

    try:
        print("Uploading GeoJSON file...")
        input_button = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, "/html/body/main/div/div[1]/div/div[1]/div/div[3]/div/div[2]/div/div[1]/div/div[4]"))
        )
        input_button.click()

        textarea = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "/html/body/main/div/div[1]/div/div[2]/div/div/div/div[3]/div[4]/div[1]/div/div[3]/div/div/div/div[6]/input"))
        )
        textarea.click()

        pyperclip.copy(geojson_text)
        actions = ActionChains(driver)
        actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL)
        actions.send_keys(Keys.RETURN)
        actions.perform()
        print("✅ Pasted GeoJSON and submitted.")

        print("Waiting for LUCA to process data...")
        popout_icon_xpath = "/html/body/main/div/div[1]/div/div[2]/div/div/div/div[3]/div[12]/div[1]/div/div[2]/div/div/div[1]"
        popout_icon = WebDriverWait(driver, 300).until(
            EC.element_to_be_clickable((By.XPATH, popout_icon_xpath))
        )
        popout_icon.click()

        print("Switching to pop-out window...")
        driver.switch_to.window(driver.window_handles[-1])

        # Download CSV
        download_csv_xpath = "/html/body/div[1]/a[3]/button"
        WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.XPATH, download_csv_xpath))
        ).click()
        print("✅ CSV Downloaded.")

        # Download PNG
        download_png_xpath = "/html/body/div[1]/a[1]/button"
        WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.XPATH, download_png_xpath))
        ).click()
        print("✅ PNG Downloaded.")

        time.sleep(10)

        # ✅ Close popout and go back to main page
        driver.close()
        driver.switch_to.window(driver.window_handles[0])

        # ✅ Click "Hide Chart" button
        hide_chart_xpath = "/html/body/main/div/div[1]/div/div[2]/div/div/div/div[3]/div[12]/div[1]/div/div[1]/div"
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, hide_chart_xpath))
        ).click()
        print("✅ Chart hidden.")

        # ✅ Take screenshot
        screenshot_path = download_dir / f"{geojson_path.stem}_map.png"
        driver.save_screenshot(str(screenshot_path))
        print(f"📸 Screenshot saved: {screenshot_path}")
        
    except Exception as e:
        print(f"❌ Error during processing: {e}")

    print("📄 Renaming output files with project name...")
    basename = geojson_path.stem
    for ext in [".csv", ".png"]:
        old_file = Path(download_dir) / f"ee-chart{ext}"
        new_file = Path(download_dir) / f"{basename}{ext}"
        if old_file.exists():
            old_file.rename(new_file)
            print(f"Renamed: {old_file} → {new_file}")
        else:
            print(f"⚠️ File not found: {old_file}")


def main():
    parser = argparse.ArgumentParser(description="Run LUCA processing with one input folder.")
    parser.add_argument("--input", required=True, help="Path to folder containing .shp file. All output will go here.")
    parser.add_argument("--tolerance", type=float, default=0.0005, help="Simplification tolerance (default: 0.0005)")
    args = parser.parse_args()
    to = args.tolerance
    folder = Path(args.input)
    os.makedirs(folder, exist_ok=True)

    # Find shapefile
    shapefiles = list(folder.glob("*.shp"))
    if not shapefiles:
        print("❌ No shapefile found in input directory.")
        return

    shapefile_path = shapefiles[0]
    geojson_path = convert_shapefile_to_geojson(shapefile_path, to)

    # Setup browser and run
    driver = setup_browser(folder)
    process_geojson_file(driver, geojson_path, folder)
    driver.quit()


if __name__ == "__main__":
    main()
