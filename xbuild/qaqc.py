import requests, geopandas as gpd, shapely, numpy as np, gdown, zipfile, os

class FLE_QAQC:
    def __init__(self,fire_year=2018,min_vert=4,invalid_incident_names=['erase','test','none']):
        #REST urls
        self._perm_url={
            'rda_hist_url':"https://services3.arcgis.com/T4QMspbfLg3qTGWY/ArcGIS/rest/services/InterAgencyFirePerimeterHistory_All_Years_View/FeatureServer", #This URL is for the Wildland Fire Management Research, Development, and Application team's Interagency fire perimeter historical dataset
            'nifc_hist_url':"https://services3.arcgis.com/T4QMspbfLg3qTGWY/ArcGIS/rest/services/WFIGS_Interagency_Perimeters/FeatureServer",   #the URL address of the Historic WFIGS Wildland Fire Perims
            'nifc_url':"https://services3.arcgis.com/T4QMspbfLg3qTGWY/ArcGIS/rest/services/WFIGS_Interagency_Perimeters_YearToDate/FeatureServer",   #the URL address of the 2024 To Date WFIGS Wildland Fire Perims
        }
        self._opr_url={
            2018:['https://services3.arcgis.com/T4QMspbfLg3qTGWY/ArcGIS/rest/services/National_Incident_Feature_Service_2018/FeatureServer',1],
            2019:['https://services3.arcgis.com/T4QMspbfLg3qTGWY/ArcGIS/rest/services/2019_NIFS_OpenData/FeatureServer',0],
            2020:['https://www.arcgis.com/sharing/rest/content/items/ea843f7f091f4c7f9743798b64c864be/data',-1],
            2021:['https://www.arcgis.com/sharing/rest/content/items/af727c41d79643b091cee372233110d4/data',-1],
            2022:['https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/Operational_Data_Archive_2022/FeatureServer',5],
            2023:['https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/Operational_Data_Archive_2023/FeatureServer',5]
        }
        self._outperm = None
        self._opr_event = None
        self._fire_year=fire_year
        self._min_vert=min_vert
        self._rinc=invalid_incident_names
    


    @property
    def fire_year(self):
        #the year of the fires you want to query
        return self._fire_year
    
    @fire_year.setter
    def fire_year(self,value):
        self._fire_year = value
    
    @property
    def min_vert(self):
        #the year of the fires you want to query
        return self._min_vert
    
    @min_vert.setter
    def min_vert(self,value):
        self._min_vert = value

    @property
    def invalid_incident(self):
        #the year of the fires you want to query
        return self._rinc
    
    @invalid_incident.setter
    def invalid_incident(self,value):
        self._rinc = value

    #Rest URLs
    @property
    def perimeters_urls(self):
        return self._perm_url

    @perimeters_urls.setter
    def perimeters_urls(self,value):
        self._perm_url = value

    @property
    def operations_urls(self):
        return self._opr_url

    @operations_urls.setter
    def operations_urls(self,value):
        self._opr_url=value

    
    #Download functions
    def _get_geodatabase(self,url,geo=None,outsr=None):
        '''
        downloads operations data from a given opts url if it does not exist and clips to the bounding box geo
        url = (string) url of the file to download
        geo = (list, polygon, geoseries, geodataframe) used to clip the event data
        outsr =  output spatial reference ('EPSG:4326')
        '''
        outfl = url.split('/')[-2] +'.gdb.zip'
        gdb_nm=''
        if (not os.path.exists(outfl)):
            gdown.download(url=url, output=outfl, quiet=False, fuzzy=True)
        
        with zipfile.ZipFile(outfl, "r") as zip_ref:
            gdb_nm=zip_ref.namelist()[0]
            if(not os.path.exists(gdb_nm)):
                zip_ref.extractall(".")
        
        gdf=gpd.read_file(gdb_nm,layer='EventLine',driver='OpenFileGDB',rows=1)

        if(not geo is None):
            if isinstance(geo,gpd.GeoDataFrame):
                geo = (geo.to_crs(gdf.crs)).total_bounds
            elif isinstance(geo,gpd.GeoSeries):
                geo = (geo.to_crs(gdf.crs)).total_bounds
            elif isinstance(geo,shapely.geometry.Polygon):
                geo = geo.bounds
            else:
                pass

            gdf=gpd.read_file(gdb_nm,layer='EventLine',driver='OpenFileGDB',bbox=tuple(geo))
        else:
            gdf=gpd.read_file(gdb_nm,layer='EventLine',driver='OpenFileGDB')

        print('Read in',gdf.shape[0],'records...')

        if(not outsr is None):
            gdf=gdf.to_crs(outsr)

        return gdf
    
    def _get_rest_data(self, url, geo=None,qry='1=1',layer=0,outsr=None):
        '''
        gets a geodataframe from a Feature Service given the url and optionally a bounding geometry and where clause

        url=(string) base url for the feature service
        geo=(object) a bounding box string, shapely polygon, geodataframe, or geoseries. string and shapely polygon objects are assumed to be in the same coordinate system as the feature service
        qry=(string) where clause used to subset the data
        layer= (int) the of the feature service to extract

        return a geodataframe of features and a list of object ids for features that could not be downloaded
        '''
        s_info=requests.get(url+'?f=pjson').json()
        srn=s_info['spatialReference']['wkid']
        sr='EPSG:'+str(srn)
        if isinstance(geo,gpd.GeoDataFrame):
            geo = (geo.to_crs(sr)).total_bounds
        elif isinstance(geo,gpd.GeoSeries):
            geo = (geo.to_crs(sr)).total_bounds
        elif isinstance(geo,shapely.geometry.Polygon):
            geo = geo.bounds
        else:
            pass
        if (geo is None):
            geo=""

        geo=','.join(np.array(geo).astype(str))
        url1=url+'/'+str(layer)
        l_info=requests.get(url1 + '?f=pjson').json()
        maxrcn=l_info['maxRecordCount']
        if maxrcn>100: maxrcn=100 #used to subset ids so query is not so long
        url2 = url1+'/query?'
        #print(url2,qry)
        o=requests.get(url2,{'where': qry,'geometry':geo,'geometryType': 'esriGeometryEnvelope','returnIdsOnly':'True','f': 'pjson'})
        if(o.status_code==200):
            o_info=o.json()
            if('objectIdFieldName' in o_info):
                oid_name=o_info['objectIdFieldName']
                oids=o_info['objectIds']
                numrec=len(oids)
                print('Downloading',numrec,'features...')
                fslist = []
                prbidlst=[]
                for i in range(0, numrec, maxrcn):
                    torec = i + maxrcn#-1)
                    if torec > numrec:
                        torec = numrec

                    objectIds = oids[i:torec]
                    idstr=oid_name + ' in (' + str(objectIds)[1:-1]+')'
                    #note that parameter values depend on the service
                    prm={
                        'where': idstr,
                        'outFields': '*',
                        'returnGeometry': 'true',
                        'f':'pgeojson',
                    }
                    rsp=requests.get(url2,prm)
                    if(rsp.status_code==200):
                        jsn=rsp.json()
                        if('features' in jsn):
                            ftrs=jsn['features']
                            fslist.append(gpd.GeoDataFrame.from_features(ftrs,crs=sr))
                    else:
                        print('Status code ',rsp.status_code,': Problem downloading features',i,'-',torec)
                        prbidlst.append(objectIds)
            else:
                print('Missing objectIdFieldName Key...')
                print('Here is the error',o_info['error'])
                return None,None

            outgdf=None
            if(len(fslist)>0):
                outgdf=gpd.pd.concat(fslist)
                if(not outsr is None):
                    outgdf=outgdf.to_crs(outsr)

            return outgdf, prbidlst
        else:
            print(o.status_code)
            return None,None
    
    
    def _remove_few_vertices_records(self, gdf):
        '''
        Remove geometries with too few vertices. Uses _min_vert attribute
       
        gdf=input geodataframe
        
        returns remaining rows geodataframe, removed rows geodataframe 
        '''
        crds=gdf.geometry.get_coordinates()
        crds_cnt=crds.groupby(crds.index).count()
        ch=crds_cnt['x']>self.min_vert
        ogdf=gdf[ch]
        rgdf=gdf[~ch]
        return ogdf,rgdf
    
    def _remove_invalid_fire_names(self, gdf, fldnm, name_list):
        '''
        Removes invalid fire names based on a list
        
        gdf=input geodataframe
        fldnm=string of the column name
        name_lst=list of partial values searched for in each row of the field. 
        
        returns remaining rows geodataframe, removed rows geodataframe 
        '''
        ch=gdf[fldnm].str.contains('|'.join(name_list),case=False)
        outgdf=gdf[~ch]
        rgdf=gdf[~ch]
        return outgdf,rgdf
    
    def _remove_identical_shapes(self, gdf):
        '''
        Removes identical shapes
        
        gdf=input geodataframe
        
        returns remaining rows geodataframe, removed rows geodataframe 
        '''
        gdf["geometry"] = gdf.normalize()
        ch=gdf.duplicated('geometry')
        ogdf=gdf[~ch]
        rgdf=gdf[ch]
        return ogdf,rgdf

    def _repair_geom(self,gdf):
        '''
        repairs the geometry of a geodataframe
        
        gdf=input geodataframe
        
        returns repaired geodataframe'''
        ogdf=gdf[~gdf.geometry.is_empty]
        ogdf=ogdf[~ogdf.geometry.isna()]
        ogs=ogdf.geometry.make_valid()
        ogdf.geometry=ogs
        return ogdf
    
    def _remove_na_identical(self, gdf, fld_lst=['IRWINID']):
        '''
        removes records with na and dupliated permiters based on IRWINID

        gdf=input geodataframe
        fld_lst=list of field names to look through

        returns remaining rows geodataframe, removed rows geodataframe 
        '''

        ogdf=gdf.dropna(axis=0,subset=fld_lst).drop_duplicates(fld_lst)
        rgdf=gdf[~gdf.index.isin(ogdf.index)]
        return ogdf,rgdf

    def get_data(self,geo=None,src='nifc_url'):
        '''
        Downloads sets fire perimeters and operations line event data from rest and geo-database urls for a given geographic boundary and fire year. 
        If a geometry is specified, perimeters and events will be limited to the extent of the boundary of that geometry.

        geo=(string, array, polygon, GeoSeries, GeoDataframe) used to extract extent of the geometry [xmin,ymin,xmax,ymax]

        returns geodataframes (_rda_hist,_nifc,_hist,_nifc,_opr_event)
        '''
        self._outperm=None
        self._opr_event= None
        src=src.lower()
        if(src in self.perimeters_urls):
            if(src=='rda_hist_url'):
                sql="FIRE_YEAR = " + str(self.fire_year)
                rda_hist,plst=self._get_rest_data(self.perimeters_urls[src], geo=geo,qry=sql)
                self._outperm=rda_hist.set_crs('EPSG:4326',allow_override=True) #esri:102100 is deprecated
            else:
                sql="attr_FireDiscoveryDateTime >= timestamp '"+str(self.fire_year)+"-01-01 00:00:00' And attr_FireDiscoveryDateTime <= timestamp '"+str(self.fire_year)+"-12-31 12:59:59'"
                self._outperm,plst=self._get_rest_data(self.perimeters_urls[src], geo=geo,qry=sql,outsr='EPSG:4326')

            o_url,flg=self.operations_urls[self.fire_year]
            if(flg==-1):
                self._opr_event=self._get_geodatabase(o_url,geo=geo,outsr='EPSG:4326')
            else:
                self._opr_event,plst=self._get_rest_data(o_url,geo,layer=flg,outsr='EPSG:4326')         
        
        return self._outperm,self._opr_event

    
    






