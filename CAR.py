import os
import numpy as np
from glob import glob
import pycurl
import argparse
from osgeo import gdal, ogr
import geopandas as gpd
import math
import pandas as pd

# Step 1: Read the project area shapefile
def read_project_area(shapefile_path):
    """
    Reads the shapefile containing the project area.
    """
    project_area = gpd.read_file(shapefile_path)
    if project_area.crs and project_area.crs.to_epsg() != 4326:
        print("Reprojecting project area to WGS 84...")
        project_area = project_area.to_crs(epsg=4326)
    
    return project_area

# Helper function to format tile name
def format_tile_name(lat, lon):
    
    lat_prefix = "N" if lat >= 0 else "S"
    lon_prefix = "E" if lon >= 0 else "W"
    
    # lat_rounded = math.floor(lat / 10) * 10
    # lon_rounded = math.floor(lon / 10) * 10
    
    return f"{lat_prefix}{abs(lat):02d}{lon_prefix}{abs(lon):03d}"

def calculate_area(gdf):
    minx, miny, maxx, maxy = gdf.total_bounds
    central_lon = (minx + maxx) / 2
    utm_zone = int((central_lon + 180) / 6) + 1
    is_northern = (miny + maxy) / 2 >= 0  # Check if the data is in the northern hemisphere

    # EPSG code for the UTM zone
    epsg_code = 32600 + utm_zone if is_northern else 32700 + utm_zone
    # Step 4: Reproject to UTM
    gdf_utm = gdf.to_crs(epsg=epsg_code)
    gdf_utm["area_ha"] = round(gdf_utm.geometry.area / 1e4, 2)
    
    return gdf_utm[["area_ha"]].sum().item()

# Step 2: Find and download tiles
def progress(download_t, downloaded, upload_t, uploaded):
    if download_t > 0:
        percent = downloaded / download_t * 100
        print(f"\rDownloading: {percent:.2f}% ({downloaded}/{download_t} bytes)", end='')

def find_and_download_tiles(project_area, year, output_folder):
    """
    Finds and downloads tiles that cover the project area.
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    # Calculate the bounding box of the project area
    bounds = project_area.total_bounds
    minx, miny, maxx, maxy = bounds
    
    # Determine the tile coordinates covering the bounding box
    min_tile_x = math.floor(minx / 10) * 10
    max_tile_x = math.floor(maxx / 10) * 10
    min_tile_y = math.ceil(miny / 10) * 10
    max_tile_y = math.ceil(maxy / 10) * 10
    
    # Generate a list of tiles based on the tile naming convention
    downloaded_files = []
    for lat in range(min_tile_y, max_tile_y + 10, 10):
        for lon in range(min_tile_x, max_tile_x + 10, 10):
            tile_name = format_tile_name(lat, lon)
            tile_filename = f"{tile_name}_ESACCI-BIOMASS-L4-AGB-MERGED-100m-{year}-fv5.0.tif"
            output_file = os.path.join(output_folder, tile_filename)
            
            if os.path.exists(output_file):
                print(f'Image tile downloaded already, check {output_file}')
                downloaded_files.append(output_file)
                continue
            
            tile_url = f"https://dap.ceda.ac.uk/neodc/esacci/biomass/data/agb/maps/v5.01/geotiff/{year}/{tile_filename}"
            print(f"Downloading {tile_filename} from {tile_url}...")
            
            # Download using pycurl
            try:
                with open(output_file, 'wb') as f:
                    curl = pycurl.Curl()
                    curl.setopt(curl.URL, tile_url)
                    curl.setopt(curl.WRITEDATA, f)
                    curl.setopt(curl.FOLLOWLOCATION, True)  # Follow redirects if needed
                    curl.setopt(curl.CONNECTTIMEOUT, 10)    # Timeout for connection
                    curl.setopt(curl.TIMEOUT, 300)         # Total timeout
                    curl.setopt(curl.NOPROGRESS, False)    # Enable progress function
                    curl.setopt(curl.XFERINFOFUNCTION, progress)  # Set progress function
                    curl.perform()
                    curl.close()
                downloaded_files.append(output_file)
                print(f"Downloaded {output_file}")
            except pycurl.error as e:
                print(f"Failed to download {tile_filename}: {e}")
    
    return downloaded_files

def mask_and_calculate_gdal(raster_tiles_list, shapefile_path, nodata=65535):
    """
    Masks a raster using a shapefile and calculates the sum and mean of pixel values.
    No intermediate files are created.
    """
    # Perform masking using GDAL Warp (in-memory)
    # print("Masking raster in-memory with GDAL...")
    mem_raster = gdal.Warp(destNameOrDestDS="", 
                           srcDSOrSrcDSTab=raster_tiles_list, 
                           cutlineDSName=shapefile_path,
                           cropToCutline=True,
                           dstNodata=nodata,
                           format="MEM")

    if mem_raster is None:
        raise RuntimeError("Raster masking failed.")

    # Read data from the in-memory raster
    band = mem_raster.GetRasterBand(1)
    data = band.ReadAsArray()

    # print("Calculating statistics...")
    data = data[data != nodata]

    if data.size == 0:
        print("No valid pixels found in the masked raster.")
        total_sum = 0
        mean_value = 0
    else:
        count = len(data)
        total_sum = np.sum(data)
        mean_value = np.nanmean(data)

    # Clean up memory
    mem_raster = None
    raster = None
    shapefile = None

    # print(f"Total Sum: {total_sum}, Mean Value: {mean_value}")
    return count, total_sum, mean_value

def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('-pid', '--pid', type=str, help='project ID', required=True)
    # parser.add_argument('-year', '--year', type=int, help='project start year', required=True)
    args = parser.parse_args()
    return args


# Main function
if __name__ == "__main__":
    # Input parameters
    args = parse_arguments()
    pid = args.pid
    output_folder=r'Projects/ESA/'
    
    # change the project folder when necessary
    aa_path = glob(f'Projects/CAR-Mexico/{pid}/*.shp')[0]
    pa_path = glob(f'Projects/CAR-Mexico/{pid}/*.shp')[1]
    
    # Step 1: Read the project area
    print("Reading project area...")
    aa = read_project_area(aa_path)
    print(f'Activity Area path: {aa_path}')
    print(f'Activity area size: {calculate_area(aa)} ha')
    
    pa = read_project_area(pa_path)
    print(f'Project Area path: {pa_path}')
    print(f'Project area size: {calculate_area(pa)} ha')
    
    
    aa_agb, aa_mean_agb, pa_agb, pa_mean_agb = [], [], [], []
    
    for year in [2010, 2015, 2016, 2017, 2018, 2019, 2020, 2021]:
        print(f'Year: {year}')
    # Step 2: Find and download tiles covering the project area
        print("Finding and downloading tiles...")
        tile_files = find_and_download_tiles(pa, year, output_folder)
        # Step 3: Perform statistics
        print("Extracting AGB values from images")
        
        _, total_sum, mean_value = mask_and_calculate_gdal(raster_tiles_list=tile_files, shapefile_path=aa_path)
        print(f'Year: {year}, total AGB in AA: {total_sum}, mean value: {mean_value}')
        aa_agb.append(total_sum)
        aa_mean_agb.append(mean_value)
        
        _, total_sum, mean_value = mask_and_calculate_gdal(raster_tiles_list=tile_files, shapefile_path=pa_path)
        print(f'Year: {year}, total AGB in PA: {total_sum}, mean value: {mean_value}')
        pa_agb.append(total_sum)
        pa_mean_agb.append(mean_value)
        print(' ')
    
    dataframe = pd.DataFrame({'AA_AGB_SUM': aa_agb,
                              'AA_AGB_MEAN': aa_mean_agb,
                              'PA_AGB_SUM':pa_agb,
                              'PA_AGB_MEAN':pa_mean_agb}, 
                             index=[2010, 2015, 2016, 2017, 2018, 2019, 2020, 2021])
    
    print(dataframe)
    if os.path.exists(f'Projects/CAR-Mexico/{pid}_out.csv'):
        print('please find it: Projects/CAR-Mexico/{pid}_out.csv')
    else: 
        dataframe.to_csv(f'Projects/CAR-Mexico/{pid}_out.csv')
        print(f'Export results to csv, please find it: Projects/CAR-Mexico/{pid}_out.csv')
    
    print('Using GEDI image for biomass mapping')
    GEDI_files = ['Projects/ESA/GEDI04_B_MW019MW223_02_002_02_R01000M_MU.tif']
    _, _, mean_value = mask_and_calculate_gdal(raster_tiles_list=GEDI_files, shapefile_path=aa_path, nodata=-9999)
    print(f'mean AGBD value in AA: {mean_value}')
    
    _, _, mean_value = mask_and_calculate_gdal(raster_tiles_list=GEDI_files, shapefile_path=pa_path, nodata=-9999)
    print(f'mean AGBD value in PA: {mean_value}')
    
    GEDI_files = ['Projects/ESA/GEDI04_B_MW019MW223_02_002_02_R01000M_SE.tif']
    _, _, mean_value = mask_and_calculate_gdal(raster_tiles_list=GEDI_files, shapefile_path=aa_path, nodata=-9999)
    print(f'mean SE value in AA: {mean_value}')
    
    _, _, mean_value = mask_and_calculate_gdal(raster_tiles_list=GEDI_files, shapefile_path=pa_path, nodata=-9999)
    print(f'mean SE value in PA: {mean_value}')
    
    print('Using CONAFOR for biomass mapping')
    CONAFOR_files = ['Projects/ESA/CONAFOR.tif']
    count, _, mean_value = mask_and_calculate_gdal(raster_tiles_list=CONAFOR_files, shapefile_path=aa_path, nodata=-9999)
    print(f'{count} pixels used and mean AGBD value in AA: {mean_value}')
    
    count, _, mean_value = mask_and_calculate_gdal(raster_tiles_list=CONAFOR_files, shapefile_path=pa_path, nodata=-9999)
    print(f'{count} pixels used and mean AGBD value in PA: {mean_value}')