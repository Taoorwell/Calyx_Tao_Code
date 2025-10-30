 # load geemap and other packages
import argparse
import os
import ee
import geemap
from glob import glob
import pandas as pd
import numpy as np
import geopandas as gpd

# crs conversion
def crs_conversion(project_area_path):
    project_df = gpd.read_file(project_area_path)
    # print(f'original crs:{project_df.crs}')
    
    project_df_wgs84 = project_df.to_crs(epsg=4326)
    # print(f'new crs: {project_df_wgs84.crs}')
    
    centroid = project_df_wgs84.unary_union.centroid
    lon = centroid.x
    utm_zone = int((lon + 180) // 6) + 1
    epsg_number = 32600+utm_zone
    # print(f'new project crs: EPSG:326{utm_zone}')
    project_df_wgs84_p = project_df_wgs84.to_crs(epsg=epsg_number)
    # remove small polygons less than 1 ha
    project_df_wgs84_p['area'] = project_df_wgs84_p.area
    project_df_filter = project_df_wgs84_p[project_df_wgs84_p['area'] > 10000]
    
    return epsg_number, project_df_filter

# some functions used later
def get_annual_loss(loss_image, loss_year, region, crs):
    loss_area = loss_image.multiply(ee.Image.pixelArea())
    loss_area_year = loss_area.addBands(loss_year).reduceRegion(
        **{'reducer': ee.Reducer.sum().group(**{'groupField': 1}),
           'geometry': region,
           'scale': 30,
           'crs':f'EPSG:{crs}',
           'bestEffort': True,
           'maxPixels': 1e9})
    loss_area_year = loss_area_year.getInfo()['groups']
    years, annual_deforestation = [], []
    for g in loss_area_year:
        years.append(g['group'])
        annual_deforestation.append(g['sum']/10000)    
    return years, annual_deforestation

def water_buffer(water_bodies, forest, dis, crs):
    distance_to_water = water_bodies.Not().cumulativeCost(source=water_bodies, maxDistance=30)
    buffered_water = distance_to_water.lte(dis)
    # Intersect the forest raster with the buffered water mask
    forest_near_water = forest.updateMask(buffered_water)
    # Calculate the total forest coverage within 30 meters of water bodies
    forest_area = forest_near_water.multiply(ee.Image.pixelArea()).reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=pa,  # Use the extent of the forest image
        scale=10,
        crs=f'EPSG:{epsg_number}',# Match the dataset resolution
        maxPixels=1e9
    )
    total_forest_area = forest_area.get('Map').getInfo()
    print(f"Total forest area within {dis} meters buffer of water: {total_forest_area / 1e4:.2f} hectares, {100 * total_forest_area / 1e4 / pa_area:.4f}%")


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('-pid', '--pid', type=str, help='project ID', required=True)
    parser.add_argument('-year', '--year', type=int, help='project start year', required=True)
    args = parser.parse_args()
    return args


map_class_table = {10: 'Tree Cover',
                   20: 'Shrubland',
                   30: 'Grassland',
                   40: 'Cropland',
                   50: 'Built-up',
                   60: 'Bare/sparse vegetation',
                   70: 'Snow and ice',
                   80: 'Permanent water bodies',
                   90: 'Herbaceous wetland',
                   95: 'Mangroves',
                   100: 'Moss and lichen'}
    
if __name__ == '__main__':
    # initial ee
    ee.Initialize()
    
    # add args
    args = parse_arguments()
    year = args.year
    new_path = f'Projects/ACR/{args.pid}/{args.pid}_wgs84_p_1ha.shp'
    if os.path.exists(new_path):
        project_df = gpd.read_file(new_path)
        crs = project_df.crs
        epsg_number = str(crs).split(':')[-1]
    else:
        file_path = glob(f"Projects/ACR/{args.pid}/*.shp")[0]
        # load shapefile with geopandas and convert its crs to utm
        epsg_number, project_df_filter = crs_conversion(file_path)
        project_df_filter.to_file(new_path)
    
    # loading project shapefile
    print(' ')
    print("Uploading project shapefile to GEE")
    pa = geemap.shp_to_ee(new_path)
    pa_area = round(pa.geometry().area(1).getInfo()/10000, 2)
    print(f"Project shapefile: {new_path.split('/')[-1]} uploaded!") 
    print(f"Project area: {pa_area} ha, or {pa_area * 2.47:.2f} acres")
    print(" ")
    
    # loading all datasets
    print('Loading ALL datasets available...')
    print('Loading GFW (30m), DEM (10m), ESA WorldCover (10m)')
    print('Loading ESA Biomass (100m), ETH_Global Canopy Height (10m) and WDPA (polygons) datasets')
    
    # GFW
    gfc = ee.Image(r'UMD/hansen/global_forest_change_2023_v1_11')
    # tree loss 
    gfc_loss_image = gfc.select(['loss'])
    # tree loss year (range from 1 to 21), base year is 2000.
    gfc_loss_year = gfc.select(['lossyear'])
    
    # DEM
    dataset = ee.Image('USGS/3DEP/10m')
    elevation = dataset.select('elevation')
    slope = ee.Terrain.slope(elevation)
    
    # ESA land cover
    dataset = ee.ImageCollection('ESA/WorldCover/v100').first()
    water_bodies = dataset.eq(80)
    forest = dataset.eq(10)
    
    # ESA biomass 
    # Loading biomass map and tree height map for imminent harvest analysis
    agb = ee.ImageCollection("projects/sat-io/open-datasets/ESA/ESA_CCI_AGB")
    agb_2010 = agb.filter(ee.Filter.date('2010-01-01','2011-01-01')).first().select(['AGB'])
    # agb_2017 = agb.filter(ee.Filter.date('2017-01-01','2018-01-01')).first().select(['AGB'])
    # agb_2018 = agb.filter(ee.Filter.date('2018-01-01','2019-01-01')).first().select(['AGB'])
    # agb_2019 = agb.filter(ee.Filter.date('2019-01-01','2020-01-01')).first().select(['AGB'])
    agb_2020 = agb.filter(ee.Filter.date('2020-01-01','2021-01-01')).first().select(['AGB'])
    
    # tree height map
    canopy_height = ee.Image("users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1")
    print(' ')
    
    # Protection area dataset
    wdpa = ee.FeatureCollection('WCMC/WDPA/current/polygons')
    
    print('##########Using GFW to check prior logging######################################')
    pa_years_def_gfc, pa_annual_deforestation_gfc = get_annual_loss(gfc_loss_image, gfc_loss_year, pa, epsg_number)
    df_gfc = pd.DataFrame({'Def_PA': pa_annual_deforestation_gfc}, index=[d+2000 for d in pa_years_def_gfc])
    df_gfc['Def_PA_rate (%)'] = df_gfc['Def_PA'] * 100 / pa_area
    print(df_gfc)
    print(f"from 2000 to {year}, the mean deforestation rate in PA: {df_gfc.loc[df_gfc.index <= year, 'Def_PA_rate (%)'].mean():.2f} %")
    print(' ')
    # to do
    print('##########Using slope from DEM to check forever unsuitable cut-off area##########')
    # Digital elevation model (DEM) for forever unsuitable harvest analysis
    # slope and extreme analysis
    histogram = slope.reduceRegion(reducer=ee.Reducer.fixedHistogram(0, 90, 18), 
                                   geometry=pa, scale=10, crs=f'EPSG:{epsg_number}', maxPixels=1e9)
    hist_data = histogram.get('slope').getInfo()
    df = pd.DataFrame(hist_data, columns=['Slope [v, v+5)', 'Frequency'])
    df['Percent (%)'] = (df['Frequency'] / df['Frequency'].sum()) * 100
    df['CumulativeP (%)'] = df['Percent (%)'].cumsum()
    print(df)
    # print(f"Areas with Slope > 25 degrees: {round(100-df.loc[df['Slope [v, v+5)'] == 20]['CumulativeP (%)'].item(), 2)} %")
    # to do plot
    print('')
    
    print('##########Using ESA land cover to calculate the land cover composition in PA######')
    # land cover composition in project area
    landcover_counts = dataset.reduceRegion(reducer=ee.Reducer.frequencyHistogram(), 
                                            geometry=pa, scale=10, crs=f'EPSG:{epsg_number}', maxPixels=1e9)
    class_counts = landcover_counts.get('Map').getInfo()
    df = pd.DataFrame(list(class_counts.items()), columns=['LandCoverID', 'PixelCount'])
    df['Percentage (%)'] = (df['PixelCount'] / df['PixelCount'].sum()) * 100
    df['LandCoverClass'] = [map_class_table[int(i)] for i in df['LandCoverID']]
    print(df)
    print(' ')
    
    print('##########Using water and forest class in ESA to calculate near-water forests in PA#######')
    # Near-water forest areas
    print('66 feet buffer: ')
    water_buffer(water_bodies, forest, 20, epsg_number)
    print('100 feet buffer: ')
    water_buffer(water_bodies, forest, 30, epsg_number)
    print('')
    
    # biomass 
    print('##########Using ESA 100m biomass and ETH global canopy height 10m to calculate imminent harvest areas in PA')
    histogram = agb_2010.reduceRegion(reducer=ee.Reducer.fixedHistogram(0, 450, 45), 
                                      geometry=pa, scale=100, crs=f'EPSG:{epsg_number}', maxPixels=1e9)
    hist_data = histogram.get('AGB').getInfo()
    df = pd.DataFrame(hist_data, columns=['Biomass (Mg/ha) [v, v+10)', 'Frequency'])
    df['Percent (%)'] = (df['Frequency'] / df['Frequency'].sum()) * 100
    df['CumulativeP (%)'] = df['Percent (%)'].cumsum()
    print(df)
    print(f"Areas with biomass > 270 Mg/ha: {round(100-df.loc[df['Biomass (Mg/ha) [v, v+10)'] == 230]['CumulativeP (%)'].item(), 2)} %")
    # to do plot
    print(' ')
    # tree height
    histogram = canopy_height.reduceRegion(reducer=ee.Reducer.fixedHistogram(0, 50, 10), 
                                           geometry=pa, crs=f'EPSG:{epsg_number}', scale=10, maxPixels=1e9)
    hist_data = histogram.get('b1').getInfo()
    df = pd.DataFrame(hist_data, columns=['Tree Height (m) [v, v+5)', 'Frequency'])
    df['Percent (%)'] = (df['Frequency'] / df['Frequency'].sum()) * 100
    df['CumulativeP (%)'] = df['Percent (%)'].cumsum()
    print(df)
    print(f"Areas with tree height > 30 m: {round(100-df.loc[df['Tree Height (m) [v, v+5)'] == 25]['CumulativeP (%)'].item(), 2)} %")
    # to do plot
    print('')
    
    print('###########Using WDPA (polygon) dataset for calculating protection areas in PA##########')
    wdpa_filtered = wdpa.filterBounds(pa.geometry())
    overlap = wdpa_filtered.map(lambda feature: feature.set('ha', feature.intersection(pa.geometry()).area(1).divide(1e4)))
    total_overlap_area = overlap.aggregate_sum('ha').getInfo()
    print(f"Total protection area in PA: {total_overlap_area:.2f} ha, around {100 * total_overlap_area/pa_area} % PA area")
    print('Datasets used and related links:')
    print('1. Historical deforestation trend, Global Forest Change, link: https://storage.googleapis.com/earthenginepartners-hansen/GFC-2023-v1.11/download.html')
    print('2. Slope analysis, USGS 3DEP 10m National Map, link: https://developers.google.com/earth-engine/datasets/catalog/USGS_3DEP_10m')
    print('3. Landcover analysis, ESA Worldcover V100, link:https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v100')
    print('4. Biomass analysis, ESA CCI Global Forest Above Ground Biomass, link: https://gee-community-catalog.org/projects/cci_agb/')
    print('5. Tree canopy Height dataset 1, ETH Global Sentinel-2 10m Canopy Height, link: https://nlang.users.earthengine.app/view/global-canopy-height-2020')
    print('6. Tree canopy height dataset 2, META High Resolution 1m Global Canopy Height Maps, link:https://meta-forest-monitoring-okw37.projects.earthengine.app/view/canopyheight')
    print('7. Protected area dataset, World Database on Protected Areas, link:https://developers.google.com/earth-engine/datasets/catalog/WCMC_WDPA_current_polygons')
    