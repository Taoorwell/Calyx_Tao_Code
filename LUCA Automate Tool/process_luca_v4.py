import os
import time
import argparse
import shutil
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
            geom_type = geom.geom_type
            if geom_type == 'Point':
                x, y = geom.coords[0][:2]
                return type(geom)((x, y))
            elif geom_type in ['LineString', 'LinearRing']:
                return type(geom)([(x, y) for x, y, *_ in geom.coords])
            elif geom_type == 'Polygon':
                shell = [(x, y) for x, y, *_ in geom.exterior.coords]
                holes = [[(x, y) for x, y, *_ in hole.coords] for hole in geom.interiors]
                return type(geom)(shell, holes)
            elif geom_type.startswith('Multi') or geom_type == 'GeometryCollection':
                return type(geom)([drop_z(part) for part in geom.geoms])
        return geom

    gdf["geometry"] = gdf["geometry"].apply(drop_z)

    # Convert to WGS84
    if gdf.crs != "EPSG:4326":
        print(f"🌍 Converting CRS from {gdf.crs} to EPSG:4326...")
        gdf = gdf.to_crs(epsg=4326)

    # Simplify geometries
    print(f"🧹 Simplifying geometries with tolerance={tolerance}...")
    gdf["geometry"] = gdf["geometry"].simplify(tolerance=tolerance, preserve_topology=True)

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
    options.add_argument("--log-level=3")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    options.add_experimental_option("prefs", {
        "download.default_directory": str(download_dir),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    })
    return webdriver.Chrome(options=options)


def process_geojson_file(driver, geojson_path, download_dir):
    output_dir = geojson_path.parent
    print(f"\n📄 Processing: {geojson_path.name}")

    with open(geojson_path, 'r', encoding='utf-8') as f:
        geojson_text = f.read()

    try:
        # Click "Input Geometry" instead of reloading page
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
        actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).send_keys(Keys.RETURN).perform()
        print("✅ Pasted GeoJSON and submitted.")

        # Wait for popout button
        popout_icon_xpath = "/html/body/main/div/div[1]/div/div[2]/div/div/div/div[3]/div[12]/div[1]/div/div[2]/div/div/div[1]"
        popout_icon = WebDriverWait(driver, 120).until(
            EC.element_to_be_clickable((By.XPATH, popout_icon_xpath))
        )
        popout_icon.click()

        # Switch to pop-out window
        driver.switch_to.window(driver.window_handles[-1])

        # Download CSV
        WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/a[3]/button"))
        ).click()

        # Download PNG
        WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/a[1]/button"))
        ).click()
        print("✅ CSV & PNG downloaded.")

        time.sleep(5)  # Wait for downloads

        # Move and rename to output folder
        for ext in [".csv", ".png"]:
            src = Path(download_dir) / f"ee-chart{ext}"
            dst = output_dir / f"{geojson_path.stem}{ext}"
            if src.exists():
                if dst.exists():
                    dst.unlink()
                shutil.move(str(src), str(dst))
                print(f"Moved: {src} → {dst}")
            else:
                print(f"⚠️ Missing file: {src}")

        # Close chart and take screenshot
        driver.close()
        driver.switch_to.window(driver.window_handles[0])
        hide_chart_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "/html/body/main/div/div[1]/div/div[2]/div/div/div/div[3]/div[12]/div[1]/div/div[1]/div"))
        )
        hide_chart_button.click()
        time.sleep(2)
        screenshot_path = output_dir / f"{geojson_path.stem}_map.png"
        driver.save_screenshot(str(screenshot_path))
        print(f"📸 Screenshot saved: {screenshot_path}")

    except Exception as e:
        print(f"❌ Error during processing {geojson_path.name}: {e}")
        # Ensure we get back to main LUCA window
        if len(driver.window_handles) > 1:
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
        raise


def main():
    parser = argparse.ArgumentParser(description="Run LUCA batch processing.")
    parser.add_argument("--input", required=True, help="Path to main folder with project subfolders.")
    parser.add_argument("--tolerance", type=float, default=0.0005)
    args = parser.parse_args()

    main_folder = Path(args.input)
    temp_download_dir = main_folder / "_downloads_temp"
    temp_download_dir.mkdir(exist_ok=True)

    driver = setup_browser(temp_download_dir)
    driver.get("https://global-forest-structure.projects.earthengine.app/view/luca-viewer")
    time.sleep(5)

    for subfolder in [f for f in main_folder.iterdir() if f.is_dir()]:
        print(f"\n➡️ Project: {subfolder.name}")
        try:
            shapefiles = list(subfolder.glob("*.shp"))
            if not shapefiles:
                print("❌ No shapefile found, skipping.")
                continue
            shapefile_path = shapefiles[0]

            geojson_path = subfolder / f"{shapefile_path.stem}.geojson"
            csv_path = subfolder / f"{shapefile_path.stem}.csv"
            png_path = subfolder / f"{shapefile_path.stem}.png"
            # if geojson_path.exists() and csv_path.exists() and png_path.exists():
            #     print("✅ All outputs exist, skipping.")
            #     continue

            # if not geojson_path.exists():
            geojson_path = convert_shapefile_to_geojson(shapefile_path, args.tolerance)

            process_geojson_file(driver, geojson_path, temp_download_dir)

        except Exception as e:
            print(f"❌ Error in {subfolder.name}: {e}")
            driver.quit()
            # restart driver
            driver = setup_browser(temp_download_dir)
            driver.get("https://global-forest-structure.projects.earthengine.app/view/luca-viewer")
            time.sleep(5)
            continue

    driver.quit()
    print("\n🎉 Batch processing finished.")


if __name__ == "__main__":
    main()
