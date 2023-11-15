# -*- coding: utf-8 -*-
"""
Name: User Fire Perimeter Input QAQC
Authors: Alex Arkowitz 
Date Created: 01/31/2023

Limitations:
Compatible with Python 3.x and ArcGIS Pro environments only which can be a limitation if the script is used in different versions of the software where the tools may have been updated or deprecated.
Assumes input datasets follow standard NIFC schemas.
The script is designed for National Interagency Fire Center specific fire-related datasets, limiting its applicability to other types of spatial analyses without significant modification
There may be hardcoded paths and URLs, which may change over time, thus requiring manual updates to the script.
The processing power required and the need for a stable internet connection also play a role in the tool's performance and capabilities.

Usage: This tool should be used to conduct QAQC on NIFC (National Interagency Fire Center) public perimeter datasets to identify issues such as duplicate perimeters with different attribution.
To use this tool, users will input a series of parameters including dataset selection and an optional XY tolerance for duplicate shape identification.

Description: The geoprocessing tool is adept at facilitating wildfire management efforts through the acquisition and analysis of fire perimeter data from various sources.
The tool is capable of downloading perimeter data directly from the National Interagency Fire Center (NIFC) Open Data portal, including datasets like the
Wildland Fire Incident Geodatabase (WFIGS) Historical Perimeters and Research and Development Application (RDA) Team datasets.
In addition to leveraging these public datasets, the tool accommodates user-provided data, adding a layer of customization and flexibility for local analysis needs.
Once the data is sourced, the tool ensures that it conforms to the Geodetic Coordinate System North American Datum of 1983 (GCS NAD83) and undertakes a geometry repair process.
The quality assurance and quality control (QAQC) phase of the workflow is multifaceted, beginning with the identification of features based on vertex count.
This is particularly useful for singling out automatically generated triangular features, which in the past, were common artifacts in fire perimeter datasets.
A key feature of the tool is the identification of identical feature shapes, which is instrumental in detecting duplicate data entries that could skew analysis results.
Users can set an XY tolerance in meters to control the sensitivity of this identification process, with the default tolerance being zero for exact shape matching.
The tool further enhances data integrity by scanning the incident name field for potentially invalid entries, such as "Test" incidents or other user-specified keywords.
This step is vital in purging the dataset of any placeholders or erroneous entries that could affect the reliability of the analysis.
Additionally, the script includes an optional geoprocessing step that selects and flags fire perimeters falling outside the United States and its territories.
This capability is crucial in identifying and rectifying potential projection issues, ensuring the geographical relevance and accuracy of the dataset for stakeholders.
The most important step in this tool in relation to the fireline engagement metrics workflow is the duplicate shape analysis which can identify perimeters that have different attribution for the same shape and location.
"""
# Import necessary libraries
import arcpy, os, urllib, sys, requests, traceback
from zipfile import ZipFile
from sys import argv
from datetime import datetime, timezone
from arcpy import metadata as md
# Define input parameters for the geoprocessing tool
DownloadTrigger = arcpy.GetParameterAsText(0) # Boolean: Determines whether to download data, default is "false" #Required
DownloadSelection = arcpy.GetParameterAsText(1) # Boolean: Determines which dataset to download, default is "false" #Required
user_fire_perimeters = arcpy.GetParameter(2)  # Feature Set: Input parameter for user-provided fire perimeters #Optional
UserInputTextName = arcpy.GetParameterAsText(3) # String: Name for user-provided data #Required
FireYear = arcpy.GetParameterAsText(4) # Double: Input for a specific year, default is None #Optional


# If FireYear is not provided, set it to None
if not FireYear:
    FireYear = None
FieldFireName = arcpy.GetParameterAsText(5) # String: Field name for filtering data, default is "attr_IncidentName" #Required
# If FieldFireName is not provided, set a default value
if not FieldFireName:
    userinputinvalidnametext = "attr_IncidentName"
userinputinvalidnametext = arcpy.GetParameterAsText(6) # String: Used in SQL query, default is "jjjjjjjj" #Optional
# If userinputinvalidnametext is not provided, set a default value
if not userinputinvalidnametext:
    userinputinvalidnametext = "jjjjjjjj"
Identicalshapetolerance = arcpy.GetParameterAsText(7) # Double: Tolerance for identical shapes, default is 25 #Optional
# If Identicalshapetolerance is not provided, set it to 25
if not Identicalshapetolerance:
    Identicalshapetolerance = 25
VtxCntTrigger = arcpy.GetParameterAsText(8)# Boolean: Determines whether to count vertices, default is "false" #Optional
# Set VerticesCount and UserIntersectTrigger based on VtxCntTrigger
if VtxCntTrigger == "true":
    VerticesCount = 4
UserIntersectTrigger = "false"

###-Variables-###
try:
    # Grab & Format system date & time
    dt = datetime.now()
    datetime = dt.strftime("%Y%m%d_%H%M")
    #PC Directory
    scrptfolder = os.path.dirname(__file__) #Returns the UNC of the folder where this python file sits
    folder_lst = os.path.split(scrptfolder) #make a list of the head and tail of the scripts folder
    local_root_fld = folder_lst[0] #Access the head (full directory) where the scripts folder resides
    webdwnld_fgdb = os.path.join(local_root_fld,"Output","Output.gdb")
    scratchworkspace = os.path.join(local_root_fld,"ScratchWorkspace","scratch.gdb")
    scratchfolder = os.path.join(local_root_fld,"ScratchWorkspace")
    localoutputws = os.path.join(local_root_fld,"Output","Output.gdb")
    rawdatastoragegdb = os.path.join(local_root_fld,"NIFC_DL_RawDataArchive","RawDLArchive.gdb")
    #Input for metadata to attribute to output
    QAQCsourcemetadatapath = os.path.join(local_root_fld,"Metadata","Perimeters_QAQC.xml")
    #Input for outside of USA perimeters
    #USA5kmBuffer = os.path.join(scratchworkspace,"USA5kmBuffer")
    #NIFC NIFS URLS. These may change so please manually update these as needed.
    RDA_FirePerimeterHistURL = "https://opendata.arcgis.com/api/v3/datasets/e02b85c0ea784ce7bd8add7ae3d293d0_0/downloads/data?format=shp&spatialRefId=4326&where=1%3D1" #This URL is for the Wildland Fire Management Research, Development, and Application team's Interagency fire perimeter historical dataset
    nifc_pbl_fullhistory_url = "https://opendata.arcgis.com/api/v3/datasets/5e72b1699bf74eefb3f3aff6f4ba5511_0/downloads/data?format=fgdb&spatialRefId=4326&where=1%3D1"   #the URL address of the Historic WFIGS Wildland Fire Perims
    nifc_pbl_YTD_url = "https://opendata.arcgis.com/api/v3/datasets/7c81ab78d8464e5c9771e49b64e834e9_0/downloads/data?format=fgdb&spatialRefId=4326"   #the URL address of the 2023 To Date WFIGS Wildland Fire Perims

    #Output Names - Conditionally Set
    #If user wants to use their own dataset these are the variables it will use
    if DownloadTrigger == "false":
        rawdata = (os.path.join(rawdatastoragegdb,"Raw_UserInput"+datetime))
        All_Dups_Datetime= UserInputTextName+"_AllDupls_"+datetime+"_"+str(Identicalshapetolerance)+"MetersXYTolerance"
        DuplicatedAcreageTable = UserInputTextName+"_Dupl_Acrg_"+datetime+"_"+str(Identicalshapetolerance)+"MetersXYTolerance"
        DuplicatedAcreage = UserInputTextName+"_TotalDuplAcreage_"+datetime+"_"+str(Identicalshapetolerance)+"MetersXYTolerance"
        UserDupsStats = UserInputTextName+"_UserIntersect_DuplAcreage_"+datetime+"_"+str(Identicalshapetolerance)+"MetersXYTolerance"
        UserDups = UserInputTextName+"_UserIntersect_Dupls_"+datetime+"_"+str(Identicalshapetolerance)+"MetersXYTolerance"
        InvldNameOutput = UserInputTextName+"_InvalidName_"+datetime
        IRWIN_ID_Field_Dups = UserInputTextName+"_IRWINID_Duplicates_"+datetime
        PreDissAcreageTable = UserInputTextName+"_TtlAcrg_"+datetime
        if VtxCntTrigger == "true":
            vtxoutput = UserInputTextName+"_VerticiesCountOutput_"+datetime+"_"+str(VerticesCount)+"VrtcNum"
        final_arch_fc_nm = UserInputTextName+"_UserInputFirePerimeters_"+datetime
    #If user wants to use the NIFC Full History dataset these are the variables it will use
    if DownloadSelection == "Wildland Fire Perimeters (WFIGS) Full History":
        rawdata = (os.path.join(rawdatastoragegdb,"Raw_WFIGS_FullHist_"+datetime))
        All_Dups_Datetime= "NIFC_WFIGS_FullHistory_AllDupls_"+datetime+"_"+str(Identicalshapetolerance)+"MetersXYTolerance"
        DuplicatedAcreageTable = "NIFC_WFIGS_FullHistory_Dupl_Acrg_"+datetime+"_"+str(Identicalshapetolerance)+"MetersXYTolerance"
        DuplicatedAcreage = "NIFC_WFIGS_FullHistory_TotalDuplAcreage_"+datetime+"_"+str(Identicalshapetolerance)+"MetersXYTolerance"
        UserDupsStats = "NIFC_WFIGS_FullHistory_Intersect_DuplAcreage_"+datetime+"_"+str(Identicalshapetolerance)+"MetersXYTolerance"
        UserDups = "NIFC_WFIGS_FullHistory_Intersect_Dups_"+datetime+"_"+str(Identicalshapetolerance)+"MetersXYTolerance"
        InvldNameOutput = "NIFC_WFIGS_FullHistory_InvalidName_"+datetime
        IRWIN_ID_Field_Dups = "NIFC_WFIGS_FullHistory_IRWINID_Duplicates_"+datetime
        PreDissAcreageTable = "NIFC_WFIGS_FullHistory_TtlAcrg_"+datetime
        if VtxCntTrigger == "true":
            vtxoutput = "NIFC_WFIGS_FullHistory_VerticiesCountOutput_"+datetime+"_"+str(VerticesCount)+"VrtcNum"
        final_arch_fc_nm = "NIFC_WFIGS_FullHistory_QAQC_"+datetime
        if FireYear is not None:
            final_arch_fc_nm = "NIFC_WFIGS_FullHistory_CY"+FireYear+"_QAQC_"+datetime
        if FireYear == None:
            final_arch_fc_nm = "NIFC_WFIGS_FullHistory_QAQC_"+datetime
    #If user wants to use the NIFC 2023 YTD dataset these are the variables it will use
    if DownloadSelection == "2023 Wildland Fire Perimeters (WFIGS) to Date":
        rawdata = (os.path.join(rawdatastoragegdb,"Raw_WFIGS2023_ToDate_"+datetime))
        All_Dups_Datetime= "NIFC_WFIGS_2023ToDate_AllDupls_"+datetime+"_"+str(Identicalshapetolerance)+"MetersXYTolerance"
        DuplicatedAcreageTable = "NIFC_WFIGS_2023ToDate_Dupl_Acrg_"+datetime+"_"+str(Identicalshapetolerance)+"MetersXYTolerance"
        DuplicatedAcreage = "NIFC_WFIGS_2023ToDate_TotalDuplAcreage_"+datetime+"_"+str(Identicalshapetolerance)+"MetersXYTolerance"
        UserDupsStats = "NIFC_WFIGS_2023ToDate_Intersect_DuplAcreage_"+datetime+"_"+str(Identicalshapetolerance)+"MetersXYTolerance"
        UserDups = "NIFC_WFIGS_2023ToDate_Intersect_Dups_"+datetime+"_"+str(Identicalshapetolerance)+"MetersXYTolerance"
        InvldNameOutput = "NIFC_WFIGS_2023ToDate_InvalidName_"+datetime
        IRWIN_ID_Field_Dups = "NIFC_WFIGS_2023ToDate_IRWINID_Duplicates_"+datetime
        PreDissAcreageTable = "NIFC_WFIGS_2023ToDate_TtlAcrg_"+datetime
        if VtxCntTrigger == "true":
            vtxoutput = "NIFC_WFIGS_2023ToDate_VerticiesCountOutput_"+datetime+"_"+str(VerticesCount)+"VrtcNum"
        final_arch_fc_nm = "NIFC_WFIGS_2023ToDate_QAQC_"+datetime
    #If user wants to use the Wildland Fire Management Research, Development, and Application team's Interagency fire perimeter historical dataset
    if DownloadSelection == "RDA Team Interagency Fire Perimeter Historical Dataset":
        rawdata = (os.path.join(rawdatastoragegdb,"Raw_RDAFirePerimsHist_"+datetime))
        All_Dups_Datetime= "RDA_Hist_AllDupls_"+datetime+"_"+str(Identicalshapetolerance)+"MetersXYTolerance"
        DuplicatedAcreageTable = "RDA_Hist_Dupl_Acrg_"+datetime+"_"+str(Identicalshapetolerance)+"MetersXYTolerance"
        DuplicatedAcreage = "RDA_Hist_TotalDuplAcreage_"+datetime+"_"+str(Identicalshapetolerance)+"MetersXYTolerance"
        UserDupsStats = "RDA_Hist_Intersect_DuplAcreage_"+datetime+"_"+str(Identicalshapetolerance)+"MetersXYTolerance"
        UserDups = "RDA_Hist_Intersect_Dups_"+datetime+"_"+str(Identicalshapetolerance)+"MetersXYTolerance"
        InvldNameOutput = "RDA_Hist_InvalidName_"+datetime
        IRWIN_ID_Field_Dups = "RDA_Hist_IRWINID_Duplicates_"+datetime
        PreDissAcreageTable = "RDA_Hist_TtlAcrg_"+datetime
        if FireYear is not None:
            final_arch_fc_nm = "NIFC_RDA_Perims_CY"+FireYear+"_QAQC_"+datetime
        if FireYear == None:
            final_arch_fc_nm = "NIFC_RDA_Perims_AllHist_QAQC_"+datetime
        if VtxCntTrigger == "true":    
            vtxoutput = "NIFC_RDA_VerticiesCountOutput_"+datetime+"_"+str(VerticesCount)+"VrtcNum"
except:
    arcpy.AddError("Variables could not be set. Exiting...")
    print("Variables could not be set. Exiting...")
    report_error()
    sys.exit()

# Overwrite and environment
try:
    # To allow overwriting outputs change overwriteOutput option to True.
    arcpy.env.overwriteOutput = True
    # Environment settings
    arcpy.env.scratchWorkspace = scratchworkspace
    arcpy.env.workspace = localoutputws
except:
    arcpy.AddError("Evironments could not be set. Exiting...")
    print("Evironments could not be set. Exiting...")
    sys.exit()

###-Functions-###

#Function to report any errors that occur in the IDLE or ArcPro Tool message screen
def report_error():   
    # Get the traceback object
    tb = sys.exc_info()[2]
    tbinfo = traceback.format_tb(tb)[0]
    # Concatenate information together concerning the error into a message string
    pymsg = "PYTHON ERRORS:\nTraceback info:\n" + tbinfo + "\nError Info:\n" + str(sys.exc_info()[1])
    msgs = "ArcPy ERRORS:\n" + arcpy.GetMessages(2) + "\n"
    # Return python error messages for use in script tool or Python Window
    arcpy.AddMessage(pymsg)
    arcpy.AddMessage(msgs)
    print(pymsg)
    print(msgs)    

#Function to download zipfile, unzip, create a filtered feature class, and delete intermin data
def dwnld_unzip_filter(url_addrs,tozip,dwnld_fcnm,fnl_fgdb):
    #Download the Wildfire Perimeters off the web
    try:
        urllib.request.urlretrieve(url_addrs,tozip)  #This is unique to python 3... will not work if run from ArcGIS Desktop
    except:
        arcpy.AddWarning("Could not retrieve file from web URL address: "+url_addrs)
        print("Could not retrieve file from web URL address: "+url_addrs)
        report_error()
    #Unzip the fgdb, grab the fgdb name, and feature class name
    try:
        arcpy.AddMessage("...UnZipping file: "+tozip)
        zipA = ZipFile(tozip)
        nm_list = zipA.namelist()
        zipA.extractall(scratchfolder)
        nifs_fp_fgdbnm = os.path.dirname(nm_list[0]) #this gets the 'directory name' of the first item in the list of files within the zipfile. The fgdb name.
        nifs_fp_fcnm = os.path.join(scratchfolder,nifs_fp_fgdbnm,dwnld_fcnm)
        if DownloadSelection == "RDA Team Interagency Fire Perimeter Historical Dataset":
            arcpy.conversion.ExportFeatures((os.path.join(scratchfolder,"InterAgencyFirePerimeterHistory_All_Years_View")),(os.path.join(fnl_fgdb,"Perimeters")))
        else:
            arcpy.FeatureClassToFeatureClass_conversion(nifs_fp_fcnm,fnl_fgdb,"Perimeters")
        zipA.close()
    except:
        arcpy.AddWarning("Could not unzip downloaded perimeters dataset.")
        print("Could not unzip downloaded perimeters dataset.")
        report_error()
    #Cleanup interim data not needed.
    arcpy.AddMessage("...Deleting interim data.")
    try:
        os.remove(tozip)   #deleting the zip file itself
        if DownloadSelection == "RDA Team Interagency Fire Perimeter Historical Dataset":
            arcpy.management.Delete(os.path.join(scratchworkspace,"InterAgencyFirePerimeterHistory_All_Years_View.shp"))
            arcpy.management.Delete(tozip)
        else:
            arcpy.Delete_management(os.path.join(scratchfolder,nifs_fp_fgdbnm)) #deleting the fgdb unzipped into the scratch folder
    except:
        report_error()
        arcpy.AddWarning("Some interim data was not delete from the directory.")
        print("Some interim data was not delete from the directory.")

###  START SCRIPT ###

#Download the selected fire perimeters using the dwnld_unzip_filter function dependent on user choice
    #Download the Wildland Fire Perimeters (WFIGS) Full History Data
if DownloadSelection == "Wildland Fire Perimeters (WFIGS) Full History":
    try:
        print("Downloading Wildland Fire Perimeters (WFIGS) Full History...")
        arcpy.AddMessage("Downloading Wildland Fire Perimeters (WFIGS) Full History")
        temparchzip = os.path.join(scratchfolder,"NIFC_Public_WildlandFirePerims_Historical_gdb_"+datetime+".zip")
        dwnld_unzip_filter(nifc_pbl_fullhistory_url,temparchzip,"Perimeters",webdwnld_fgdb)
        user_fire_perimeters = os.path.join(webdwnld_fgdb,"Perimeters")
        # Announce Completion and final feature class name:
        arcpy.AddMessage("The downloaded NIFC Public Open Data is located in: "+webdwnld_fgdb)
        print("The downloaded  NIFC Public Open Data is located in: "+webdwnld_fgdb)
    except:
        arcpy.AddError("Error downloading and unzipping the Wildland Fire Perimeters. Exiting.")
        print("Error downloading and unzipping the Wildland Fire Perimeters. Exiting.")
        report_error()
        sys.exit()
    #Download the CY2023 'To Date' Current Wildland Fire Data
if DownloadSelection == "2023 Wildland Fire Perimeters (WFIGS) to Date":
    try:
        print("Downloading 2023 Wildland Fire Perimeters (WFIGS) to Date...")
        arcpy.AddMessage("Downloading 2023 Wildland Fire Perimeters (WFIGS) to Date")
        temparchzip = os.path.join(scratchfolder,"NIFC_CY2023_Public_WildlandFirePerims_ToDate_gdb_"+datetime+".zip")
        dwnld_unzip_filter(nifc_pbl_YTD_url,temparchzip,"Perimeters",webdwnld_fgdb)
        user_fire_perimeters = os.path.join(webdwnld_fgdb,"Perimeters")
        # Announce Completion and final feature class name:
        arcpy.AddMessage("The downloaded NIFC Public Open Data is located in: "+webdwnld_fgdb)
        print("The downloaded  NIFC Public Open Data is located in: "+webdwnld_fgdb)
    except:
        arcpy.AddError("Error downloading and unzipping the Wildland Fire Perimeters. Exiting.")
        print("Error downloading and unzipping the Wildland Fire Perimeters. Exiting.")
        report_error()
        sys.exit()
    #Download the RDA Team Interagency Fire Perimeter Historical Dataset
if DownloadSelection == "RDA Team Interagency Fire Perimeter Historical Dataset":
    try:
        print("Downloading RDA Team's Interagency Fire Perimeter Historical Dataset...")
        arcpy.AddMessage("Downloading RDA Team's Interagency Fire Perimeter Historical Dataset...")
        temparchzip = os.path.join(scratchfolder,"RDA_HistFirePerims_ToDate_gdb_"+datetime+".zip")
        dwnld_unzip_filter(RDA_FirePerimeterHistURL,temparchzip,"RDA_IntrgncyPerimHistory",webdwnld_fgdb)
        user_fire_perimeters = os.path.join(webdwnld_fgdb,"Perimeters")
        # Announce Completion and final feature class name:
        arcpy.AddMessage("The downloaded NIFC RDA Team's Interagency Fire Perimeter Historical Dataset is located in: "+webdwnld_fgdb)
        print("The downloaded NIFC RDA Team's Interagency Fire Perimeter Historical Dataset is located in: "+webdwnld_fgdb)
    except:
        arcpy.AddError("Error downloading and unzipping the Wildland Fire Perimeters. Exiting.")
        print("Error downloading and unzipping the Wildland Fire Perimeters. Exiting.")
        report_error()
        sys.exit()
    #Format the RDA data to have fields that match that of WFIGS so that it works with the rest of the script
if DownloadSelection == "RDA Team Interagency Fire Perimeter Historical Dataset":
    try:
        arcpy.management.ConvertTimeField(user_fire_perimeters,"FIRE_YEAR_","yyyy","attr_FireDiscoveryDateTime","DATE","")
        arcpy.management.AddField(user_fire_perimeters,"attr_IncidentName","TEXT",None,None,50,"","NULLABLE","NON_REQUIRED","")
        arcpy.management.CalculateField(user_fire_perimeters,"attr_IncidentName","!INCIDENT!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
        arcpy.management.AddField(user_fire_perimeters,"attr_IrwinID","TEXT",None,None,38,"","NULLABLE","NON_REQUIRED","")
        arcpy.management.CalculateField(user_fire_perimeters,"attr_IrwinID","!IRWINID!","PYTHON3","","DATE","NO_ENFORCE_DOMAINS")
    except:
        arcpy.AddError("Error Reformatting the RDA Perimeters. Exiting.")
        print("Error Reformatting the RDA Perimeters. Exiting.")
        report_error()
        sys.exit()
###Preprocessing###
'''Creates a copy of raw data, optionally creates a subset of
fire perimeters based on the Discovery date field, repairs geometry, and reports the number
of null features, and projects the dataset to GCS_WGS_1984 accordingly.'''
try:
    arcpy.AddMessage("Preprocessing Fire Perimeter Feature Class. Subsetting perimeters based on user selected year, repairing geometry, and projecting to GCS_WGS_1984 if needed.")
    print("Preprocessing Fire Perimeter Feature Class. Subsetting perimeters based on user selected year, repairing geometry, and projecting to GCS_WGS_1984 if needed.")
    # Create a copy of raw fire perimeter data before preprocessing
    arcpy.management.CopyFeatures(user_fire_perimeters, rawdata)
    # Subset fires to a calendar year based on the FireYear variable, if specified
    if FireYear is not None:
        print ("Creating a subset of fires to selected calender year: "+FireYear)
        arcpy.AddMessage("Creating a subset of fires to selected calender year: "+FireYear)
        arcpy.management.MakeFeatureLayer(rawdata, "NIFC_Perims_CYsubset", "attr_FireDiscoveryDateTime >= timestamp '"+FireYear+"-01-01 00:00:00' And attr_FireDiscoveryDateTime <= timestamp '"+FireYear+"-12-31 12:59:59'")
        arcpy.management.CopyFeatures("NIFC_Perims_CYsubset", user_fire_perimeters)    
    # Get the spatial reference of the feature class
    featureClass = (user_fire_perimeters)
    desc = arcpy.Describe(featureClass) 
    spatialRef = desc.spatialReference
    # Check if the spatial reference is GCS_WGS_1984, if not, project to GCS_WGS_1984
    if spatialRef.Name == "GCS_WGS_1984":
        arcpy.management.CopyFeatures(user_fire_perimeters, final_arch_fc_nm)
    else:
        print ("Changing Projection from Web Mercator To GCS_WGS_1984")
        arcpy.AddMessage("Changing Projection from Web Mercator To GCS_WGS_1984")
        arcpy.management.Project(user_fire_perimeters,final_arch_fc_nm,'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]',None,'PROJCS["WGS_1984_Web_Mercator_Auxiliary_Sphere",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Mercator_Auxiliary_Sphere"],PARAMETER["False_Easting",0.0],PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",0.0],PARAMETER["Standard_Parallel_1",0.0],PARAMETER["Auxiliary_Sphere_Type",0.0],UNIT["Meter",1.0]]',"NO_PRESERVE_SHAPE",None,"NO_VERTICAL")
    arcpy.management.Delete(user_fire_perimeters)
    # Report the number of features before and after deleting null geometry
    result = arcpy.GetCount_management(final_arch_fc_nm)
    countstring = str(result)
    print(countstring+" Total Features Found Before Deleting Null Geometry.")
    arcpy.AddMessage(countstring+" Total Features Found Before Deleting Null Geometry.")
    # Repair geometry and delete null geometries
    arcpy.RepairGeometry_management(final_arch_fc_nm,"DELETE_NULL")
    result = arcpy.GetCount_management(final_arch_fc_nm)
    countstring = str(result)
    print(countstring+" Total Features Found AFTER Deleting Null Geometry.")
    arcpy.AddMessage(countstring+" Total Features Found AFTER Deleting Null Geometry.")
    # If the download selection is "RDA Team Interagency Fire Perimeter Historical Dataset," delete a specific processing file
    if DownloadSelection == "RDA Team Interagency Fire Perimeter Historical Dataset":
        arcpy.management.Delete(os.path.join(scratchworkspace,"InterAgencyFirePerimeterHistory_All_Years_View.shp"))
    ## Announce Completion and final feature class name:
    arcpy.AddMessage("The preprocessed user derived fire perimeters is located: "+webdwnld_fgdb+" and is named "+final_arch_fc_nm)
    print("The preprocessed user derived fire perimeters is located: "+webdwnld_fgdb)
except:
    arcpy.AddError("Error Preprocessing the Wildland Fire Perimeters. Exiting.")
    print("Error Preprocessing the Wildland Fire Perimeters. Exiting.")
    report_error()
    sys.exit()

# Run a process to calculate the total acreage pre-dissolve
try:
    print("Calculating Acreage and Vertices for Fire Perimeter Data")
    arcpy.AddMessage("Calculating Acreage and Vertices for Fire Perimeter Data")
    arcpy.management.AddField(final_arch_fc_nm, "TotalCalculatedAcreage", "DOUBLE", None, None, None, "Total Calculated Acreage", "NULLABLE", "NON_REQUIRED", '')
    arcpy.management.CalculateField(final_arch_fc_nm, "TotalCalculatedAcreage", "!shape.geodesicArea@acres!", "PYTHON3", '', "TEXT")
    arcpy.analysis.Statistics(final_arch_fc_nm, PreDissAcreageTable, "TotalCalculatedAcreage SUM", None)
    #This next section sets the total acreage of the raw to date fire perimeters as a variable. Will be referenced later for acreage calculations
    fc = (PreDissAcreageTable)
    fields = ['SUM_TotalCalculatedAcreage']
    with arcpy.da.SearchCursor(fc, fields) as cursor:
        for row in cursor:
            PreDissAcreageMath = row[0]
    arcpy.management.Delete(PreDissAcreageTable) #Delete the output table that holds dissovled acreage to simplify output of tool

    # Analysis to identify features with a user-defined amount of vertices (triangles)
    if VtxCntTrigger == "true":
        print("Identifying Features with Less Than or Equal to "+str(VerticesCount)+" Vertices.")
        arcpy.AddMessage("Identifying Features with Less Than or Equal to "+str(VerticesCount)+" Vertices.")
        arcpy.management.AddField(final_arch_fc_nm, "VerticesCount", "LONG", None, None, None, '', "NULLABLE", "NON_REQUIRED", '')
        arcpy.management.CalculateField(final_arch_fc_nm, "VerticesCount", "!shape!.pointcount", "PYTHON3", '', "TEXT")
        arcpy.management.MakeFeatureLayer(final_arch_fc_nm, "CntVertxfeatlayer", "VerticesCount <= "+str(VerticesCount))
        #arcpy.management.CopyFeatures("CntVertxfeatlayer", vtxoutput)
        result = arcpy.GetCount_management("CntVertxfeatlayer")
        count = int(result.getOutput(0))
        if count == 0:
            print("No Features with Less Than or Equal to "+str(VerticesCount)+" Vertices Found.")
            arcpy.AddMessage("No Features with Less Than or Equal to "+str(VerticesCount)+" Vertices Found.")
            #arcpy.management.Delete(vtxoutput)
        else:
            print(str(count)+" Features with Less Than or Equal to "+str(VerticesCount)+" Vertices Found.")
            arcpy.AddMessage(str(count)+" Features with Less Than or Equal to "+str(VerticesCount)+" Vertices Found.")

    # Identify features with null or possibly invalid incident names
    try:
        print("Identifying Incidents with Null or Possible Invalid Names")
        arcpy.AddMessage("Identifying Incidents with Null or Possible Invalid Names. This includes 'Erase', 'Test', 'None', and the user input '"+userinputinvalidnametext+"'")
        # Create a list of values to check for invalid names
        lstvalues = ['erase','test','none',userinputinvalidnametext.lower()]
        sqlstring = ""
        cntvl =  0
        for value in lstvalues:
            if cntvl == 0:
                sqlstring = "lower("+FieldFireName+") LIKE '%"+value+"%' Or ("+FieldFireName+") IS NULL"
            else:
                sqlstring = sqlstring+" Or " + "lower("+FieldFireName+") LIKE '%"+value+"%' Or ("+FieldFireName+") IS NULL"
            cntvl = cntvl+1
        arcpy.management.AddField(final_arch_fc_nm,"InvalidName","TEXT")
        # Mark features with invalid names as "Yes"
        arcpy.management.MakeFeatureLayer(final_arch_fc_nm, "InvalidNameOutputLyr", str(sqlstring))
        arcpy.management.CalculateField("InvalidNameOutputLyr","InvalidName",'"Yes"',"PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
        #arcpy.management.CopyFeatures("InvalidNameOutputLyr", InvldNameOutput)
        result = arcpy.GetCount_management("InvalidNameOutputLyr")
        count = int(result.getOutput(0))
        if count == 0:
            print("No Features with Invalid Names Found. No Output Feature Class Will be Created.")
            arcpy.AddMessage("No Features with Invalid Names Found. No Output Feature Class Will be Created.")
        else:
            countstring = str(count)
            print(countstring+" Features with Null or Invalid Names Found.")
            arcpy.AddMessage(countstring+" Features with Null or Invalid Names Found.")
            arcpy.AddMessage("The Features With Invalid Names can be found in the output.")
            print("The Features With Invalid Names can be found in the output.")
    except:
        report_error()
except:
    arcpy.AddError("Error Calculating Total Pre and Post Dissolve Acres.")
    print("Error Calculating Total Pre and Post Dissolve Acres.")
    report_error()
    sys.exit()

#Run process to find duplicated IRWIN IDs 
try:
    print("Looking for Duplicated IRWIN IDs.")
    arcpy.AddMessage("Looking for Duplicated IRWIN IDs.")
    # Use the Frequency tool to count the frequency of each unique IRWIN ID
    arcpy.analysis.Frequency(final_arch_fc_nm, "FH_Perimeter_IrwinFreq", "attr_IrwinID", None)
    arcpy.management.JoinField(final_arch_fc_nm, "attr_IrwinID", "FH_Perimeter_IrwinFreq", "attr_IrwinID", "FREQUENCY")
    arcpy.management.MakeFeatureLayer(final_arch_fc_nm,"IRWIN_ID_Dups", "FREQUENCY >= 2", None)
    arcpy.management.CopyFeatures("IRWIN_ID_Dups", IRWIN_ID_Field_Dups)
    arcpy.management.DeleteField(final_arch_fc_nm, "FREQUENCY")
    arcpy.management.Delete("FH_Perimeter_IrwinFreq")
    arcpy.management.Delete("IRWIN_ID_Dups")
    arcpy.management.Delete(IRWIN_ID_Field_Dups)
    resultIRWINID = arcpy.GetCount_management(IRWIN_ID_Field_Dups)
    countIrwinID = int(resultIRWINID.getOutput(0))
    if countIrwinID == 0:
        print("No Duplicate Features with the same IRWIN ID Found")
        arcpy.AddMessage("No Duplicate Features with the same IRWIN ID Found")
    else:
        arcpy.AddMessage("Features That Share the same IRWIN ID have been found")
        print("Features That Share the same IRWIN ID have been found.")    
except:
    report_error()

# This code block runs the identical shape analysis. It then figures out how much is duplicated acreage and how much is overlapping acreage
# It creates fields in the output dataset to ID the features and the frequency.
try:
    print("Looking for Identical Incident Shapes With a XY Tolerance of "+str(Identicalshapetolerance)+" METERS")
    arcpy.AddMessage("Looking for Identical Incident Shapes With a XY Tolerance of "+str(Identicalshapetolerance)+" METERS")
    if Identicalshapetolerance != 0:
        arcpy.management.FindIdentical(final_arch_fc_nm, "Find_Identical_output_shape", "Shape", str(Identicalshapetolerance)+" METERS", 0, "ONLY_DUPLICATES")
    else:
        arcpy.management.FindIdentical(final_arch_fc_nm, "Find_Identical_output_shape", "Shape", None, 0, "ONLY_DUPLICATES")
    #Joins output from Find Identical tool to then create a field in the polygons to hold the frequency of duplicates
    print("Performing Statistical Analysis.")
    arcpy.AddMessage("Performing Statistical Analysis.")
    arcpy.analysis.Statistics("Find_Identical_output_shape", "Find_Identical_output_shape_SumStats", "FEAT_SEQ COUNT", "FEAT_SEQ")
    arcpy.management.JoinField("Find_Identical_output_shape", "FEAT_SEQ", "Find_Identical_output_shape_SumStats", "FEAT_SEQ", "FREQUENCY")
    if DownloadSelection == "RDA Team Interagency Fire Perimeter Historical Dataset":
        arcpy.management.JoinField(final_arch_fc_nm, "OBJECTID_1", "Find_Identical_output_shape", "IN_FID", "FEAT_SEQ;FREQUENCY")
    else:
        arcpy.management.JoinField(final_arch_fc_nm, "OBJECTID", "Find_Identical_output_shape", "IN_FID", "FEAT_SEQ;FREQUENCY")
    arcpy.management.AlterField(final_arch_fc_nm,"FEAT_SEQ", "DuplicateID", "DuplicateID", "LONG", 4, "NULLABLE", "DO_NOT_CLEAR")
    #Creates subset of features with shape duplicates and cleans up some data.
    arcpy.management.MakeFeatureLayer(final_arch_fc_nm, "UserInput_ToDate2021_WildlandFire_FeatLayer", "FREQUENCY > 1")
    arcpy.management.Delete("Find_Identical_output_shape")
    arcpy.management.Delete("Find_Identical_output_shape_SumStats")
    arcpy.AddMessage("Creating Subset of Duplicate Fires")
    arcpy.management.CopyFeatures("UserInput_ToDate2021_WildlandFire_FeatLayer",All_Dups_Datetime)
    arcpy.management.Delete("UserInput_ToDate2021_WildlandFire_FeatLayer")
    #Creates a field to hold duplicated acreage for perimeters
    print("Calculating Duplicated Acreage for Fire Perimeters")
    arcpy.AddMessage("Calculating Duplicated Acreage for Fire Perimeters")
    arcpy.management.AddField(All_Dups_Datetime, "TotalDuplAcreage", "DOUBLE", None, None, None, "TotalDuplAcreage", "NULLABLE", "NON_REQUIRED", '')
    arcpy.management.CalculateField(All_Dups_Datetime, "TotalDuplAcreage", "!shape.geodesicArea@acres!", "PYTHON3", '', "TEXT")
    if DownloadSelection == "RDA Team Interagency Fire Perimeter Historical Dataset":
        arcpy.analysis.Statistics(All_Dups_Datetime, "DuplSumStats", "OBJECTID_1 FIRST", "DuplicateID")
        DuplicatedSumStats = "DuplSumStats"
        arcpy.management.JoinField(All_Dups_Datetime, "OBJECTID", DuplicatedSumStats, "FIRST_OBJECTID_1", "DuplicateID;FIRST_OBJECTID_1")
        arcpy.management.MakeFeatureLayer(All_Dups_Datetime, "AllToDateDups_JoinISNotNull", "FIRST_OBJECTID_1 IS NULL")
    else:
        arcpy.analysis.Statistics(All_Dups_Datetime, "DuplSumStats", "OBJECTID FIRST", "DuplicateID")
        DuplicatedSumStats = "DuplSumStats"
        arcpy.management.JoinField(All_Dups_Datetime, "OBJECTID", DuplicatedSumStats, "FIRST_OBJECTID", "DuplicateID;FIRST_OBJECTID")
        arcpy.management.MakeFeatureLayer(All_Dups_Datetime, "AllToDateDups_JoinISNotNull", "FIRST_OBJECTID IS NULL")
    arcpy.management.Delete(DuplicatedSumStats)
    arcpy.analysis.Statistics("AllToDateDups_JoinISNotNull", DuplicatedAcreage, "TotalDuplAcreage SUM", None)
    duplfc = (DuplicatedAcreage)
    #check if any duplicates exist
    resultDuplicatedAcreage = arcpy.GetCount_management(DuplicatedAcreage)
    countDuplicatedAcreage = int(resultDuplicatedAcreage.getOutput(0))
    if countDuplicatedAcreage == 0:
        print("No Duplicate Features Found.")
        arcpy.AddMessage("No Duplicate Features Found.")
    else:
        duplfields = ['SUM_TotalDuplAcreage']
        #DuplicAcreagestr holds total duplicated acreage as a string to print later
        with arcpy.da.SearchCursor(duplfc, duplfields) as cursor:
            for row in cursor:
                DuplicAcreagestr = row[0]
        if DownloadSelection == "RDA Team Interagency Fire Perimeter Historical Dataset":
            arcpy.management.DeleteField(All_Dups_Datetime, "TotalDuplAcreage;DuplicateID_1;FIRST_OBJECTID_1", "DELETE_FIELDS")
        else:
            arcpy.management.DeleteField(All_Dups_Datetime, "TotalDuplAcreage;DuplicateID_1;FIRST_OBJECTID", "DELETE_FIELDS")
    #Delete unneeded datasets/Clean up workspace
    arcpy.management.Delete(DuplicatedAcreage)
    arcpy.management.Delete(os.path.join(localoutputws,"Perimeters"))
    arcpy.management.Delete(All_Dups_Datetime)###########################################Comment out if you want duplicates in its own FC
except:
    arcpy.AddError("Error Looking for Identical Incident Shapes")
    print("Error Looking for Identical Incident Shapes.")
    report_error()
    sys.exit()

###If user wants to identify perimeters that fall outside of US, a feature named "USA5kmBuffer" will need to be placed in the scratch workspace: os.path.join(scratchworkspace,"USA5kmBuffer")
### This portion of code identifies perimeters that fall outside of the USA
##try:
##    print("Looking for Features Outside of USA")
##    arcpy.AddMessage("Looking for Features Outside of USA")
##    arcpy.management.AddField(final_arch_fc_nm,"OutsideOfUSA","TEXT")
##    arcpy.management.MakeFeatureLayer(final_arch_fc_nm,"NIFS_Perims")
##    arcpy.management.SelectLayerByLocation("NIFS_Perims","INTERSECT",USA5kmBuffer,None,"NEW_SELECTION","INVERT")
##    
##    outofUSA = arcpy.GetCount_management("NIFS_Perims")
##    count = int(outofUSA.getOutput(0))
##    if count == 0:
##        print("No Features Found Outside of US.")
##        arcpy.AddMessage("No Features Found Outside of US.")
##        arcpy.management.DeleteField(final_arch_fc_nm, "OutsideOfUSA", "DELETE_FIELDS")
##    else:
##        print("Features Found Outside of US.")
##        arcpy.AddMessage("Features Found Outside of US.")
##        arcpy.management.CalculateField("NIFS_Perims","OutsideOfUSA",'"Yes"',"PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
##except:
##    arcpy.AddError("Error Looking for Features Outside of USA")
##    print("Error Looking for Features Outside of USA")
##    report_error()
##    sys.exit()

# Prints a summary of acreages calculated
try:
    arcpy.AddMessage("Total Fire Perimeter Acreage is "+(str(int(PreDissAcreageMath))))
    print("Total Fire Perimeter Acreage is "+(str(int(PreDissAcreageMath))))
    if countDuplicatedAcreage == 0:
        pass
    else:
        arcpy.AddMessage("Total Duplicated Acreage is "+(str(int(DuplicAcreagestr))))
        print("Total Duplicated Acreage is "+(str(int(DuplicAcreagestr))))
except:
    arcpy.AddError("Error Creating Duplicate Report.")
    print("Error Creating Duplicate Report. Exiting.")
    report_error()
    sys.exit()
# Import metadata from the specified source metadata path and save it to the final feature class
try:
    print("Writing Metadata to Output Feature Classes")
    arcpy.AddMessage("Writing Metadata to Output Feature Classes")
    tgt_item_md = md.Metadata(final_arch_fc_nm)
    tgt_item_md.importMetadata(QAQCsourcemetadatapath)
    tgt_item_md.save()
except:
    arcpy.AddError("Error Importing Metadata. Exiting.")
    print("Error Importing Metadata. Exiting.")
    report_error()
    sys.exit()


print("Script Finished Running.")
arcpy.AddMessage("Script Finished")
