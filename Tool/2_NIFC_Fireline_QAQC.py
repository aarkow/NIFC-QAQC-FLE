# -*- coding: utf-8 -*-
"""
Name: WFIGS NIFC Fire Perimeter and Fireline Processing and QAQC
Author: Alex Arkowitz @ Colorado State University - alexander.arkowitz@colostate.edu
Date Created: 02/13/2023

Limitations:
Compatible with Python 3.x and ArcGIS Pro environments only which can be a limitation if the script is used in different versions of the software where the tools may have been updated or deprecated.
Assumes input datasets follow standard NIFC schemas.
The script is designed for National Interagency Fire Center specific fire-related datasets, limiting its applicability to other types of spatial analyses without significant modification
There may be hardcoded paths and URLs, which may change over time, thus requiring manual updates to the script.
The processing power required and the need for a stable internet connection also play a role in the tool's performance and capabilities.

Usage: To be used when firelines are needed from NIFC Operations data. Visual inspection and other QAQC will need to be done on the output.

Description:
This Python script is designed to work within the ArcGIS environment, specifically leveraging the arcpy library to manipulate and analyze geospatial data related to fire perimeters and operational data.
The script contains multiple sections, each dedicated to a particular step in the process of preparing, analyzing, and refining fire-related datasets.

Initially, the script sets up the environment, defining input parameters and variables to store data paths and URLs to external data sources.
Functions are defined to report errors and download data, such as historical fire perimeters and operational data based on the year of fire incidents.
The script handles downloading, unzipping, and processing data files from specified URLs, ensuring they're in the correct format and location for subsequent analysis.
Using the variables provided, the QAQC tool downloads the selected operations data for the (calendar year) CY from NIFS public data.

Subsequent sections of the code focus on preprocessing the data, including projecting datasets to a standard coordinate system (GCS_WGS_1984), repairing geometry, and calculating geodesic areas.
A significant portion of the script is dedicated to quality control: it compares attributes between different datasets to ensure consistency in naming and identification numbers (IRWIN IDs).
Since the perimeters have two IRWIN ID fields, if the attr_irwin ID is null and the poly_irwinID is not null, the attr_irwinID that are null are taken from the populated poly_irwinIDs.
If the attr_incidentnames and attr_irwin IDs for both the firelines and the perimeters have any extra spaces found before and after the text, it will be removed.
The ops line data is then filtered to only contain: 'Completed Burnout', 'Completed Dozer Line', 'Completed Fuel Break', 'Completed Hand Line', 'Completed Mixed Construction Line',
'Completed Plow Line', 'Completed Road as Line', 'Contained Line', and 'Road as Completed Line'.
The ops line is again filtered based on the “delete this” field to delete 'Yes - Editing Mistake', 'Yes - No Longer Needed') Or FeatureStatus IN ('Proposed') Or FeatureStatus IS NULL"
The ops data IRWIN ID field is analyzed to look for missing {} brackets around the IRWIN ID. If it does not start with a “{“ then those are inserted around the IRWIN ID.
The ops data IRWIN ID field is then analyzed for length. If 'CHAR_LENGTH("IRWINID") < 36 OR CHAR_LENGTH("IRWINID") > 40' it is considered invalid as they are always (as of 2023) within that threshold.
This removes comments such as “Don’t know”, “?” ect.
The script identifies and corrects discrepancies between the fire perimeter and fireline data by considering attributes such as the incident name and the point of origin state.
This process includes buffering fire perimeters to capture nearby firelines that may not have matching attributes but are spatially related to the fire events.
The ops data line type is then analyzed and is attributed a rank as follows:
if FeatureCategory =='Completed Road as Line':  return 1
    elif FeatureCategory =='Road as Completed Line': return 1
    elif FeatureCategory =='Completed Dozer Line': return 2
    elif FeatureCategory =='Completed Hand Line': return 3
    elif FeatureCategory =='Completed Mixed Construction Line': return 4
    elif FeatureCategory =='Completed Fuel Break': return 5
    elif FeatureCategory =='Completed Burnout': return 6
    elif FeatureCategory =='Completed Plow Line': return 7
    elif FeatureCategory is None: return None
The data is then projected to GCS WGS 1984, and the geometry is repaired. Null geometry features are deleted.
A field is added to the perimeter dataset to calculate geodesic acreage.

The script addresses data integrity by removing duplicates based on attributes like shape, incident name, line type, and IRWIN ID, and by dissolving overlapping features.
The next section compares IRWIN IDs, Incident name, and POO (point of Orig) of perimeters and firelines to grab all lines outside of buffer area (done later) if they have
the same IRWIN ID and/or the same incident name within the same POO state.
The perimeter data is then brought into the scratch workspace as a copy since query tables require both datasets to be in the same gdb. 
The Ops data is intersected with a US States polygon and joined to the perimeter attributes to ID if the firelines:
    "Has Matching IRWIN and Name"
    "Has Matching IRWIN ID. Name Taken From Matching IRWIN"
    "Has Matching Inc Name in Same State. IRWIN Taken From Matching Name"
The fields are then populated accordingly. If a name or IRWIN ID was already present and overwritten, the overwritten records are stored in fields “OldName” and “OldIRWIN” accordingly.

A subset of firelines is then created that was not IDed as part of the fire due to attribution.
A buffer is created around the user input fire perimeter and all intersecting firelines are selected.
The “Flag” field is then populated accordingly:
        if (IncidentName is None and IRWINID is None): "Within Buffer but Both Inc Name and IRWIN Null. Both Changed to Match Largest Perim"
        elif (IRWINID is None and IncidentName is not None): "Within Buffer but IRWIN Null. Both Changed to Match Largest Perim"
        elif (IRWINID is not None and IncidentName is None): "Within Buffer but Inc Name Null. Both Changed to Match Largest Perim"
        elif (IRWINID is not None and IncidentName is not None): "Within Buffer but Both Inc Name and IRWIN Didnt Match. Both Changed to Match Largest Perim"
If these fields did have attribution, the “OldName” and “OldIRWIN” were populated accordingly.
Finally, the script concludes with metadata writing to the output feature classes, importing predefined metadata templates to document the datasets' sources, processing history, and other relevant information.

The final output is a set of processed, consistent, and clean geospatial datasets ready for further analysis or reporting on fire incidents and operations.
"""
#import libraries
import arcpy, os, urllib, sys, requests, traceback
from arcpy import metadata as md
from zipfile import ZipFile
from sys import argv
from datetime import datetime, timezone

# User-defined parameters for use in ArcGIS Pro
Hist_fire_perimeters = arcpy.GetParameter(0)  # Optional parameter to input feature set for historical fire perimeters.
DownloadOpsDataTrigger = arcpy.GetParameterAsText(1) # Boolean parameter to decide whether to download operational data; default is "false".
NIFC_OpsDataArchive = arcpy.GetParameter(2)  # Optional parameter to input feature set for NIFC operational data archive.
FireYear = arcpy.GetParameterAsText(3)  # Text parameter for specifying the year of the fire.
UserProvidedFireYear = arcpy.GetParameterAsText(4)  # Text parameter for user-provided fire year.
PerimBufferIntersect = arcpy.GetParameterAsText(5)  # Text parameter for perimeter buffer intersection.
FireName = arcpy.GetParameterAsText(6)  # Text parameter for the name of the fire.

###-Functions-###
#Function to report any errors that occur while running in the message screen
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
#Function to download zipfile, unzip, create a feature class, and delete intermin data
def dwnld_unzip_filter(url_addrs,tozip,dwnld_fcnm,fnl_fgdb):
    #Download the Wildfire Perimeters off of the web
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
        nifs_fp_fgdbnm = os.path.dirname(nm_list[0]) #this get the 'directory name' of the first item in the list of files within the zipfile. The fgdb name.
        nifs_fp_fcnm = os.path.join(scratchfolder,nifs_fp_fgdbnm,dwnld_fcnm)
        arcpy.FeatureClassToFeatureClass_conversion(nifs_fp_fcnm,fnl_fgdb,dwnld_fcnm)
        zipA.close()
    except:
        arcpy.AddWarning("Could not unzip downloaded dataset.")
        print("Could not unzip downloaded dataset.")
        report_error()
    #Cleanup interim data not needed.
    arcpy.AddMessage("...Deleting interim data.")
    try:
        os.remove(tozip)   #deleting the zip file itself
        arcpy.Delete_management(os.path.join(scratchfolder,nifs_fp_fgdbnm)) #deleting the fgdb unzipped into the scratch folder
    except:
        report_error()
        arcpy.AddWarning("Some interim data was not delete from the directory.")
        print("Some interim data was not delete from the directory.")

###-Variables-###
try:
    # Grab & Format system date & time
    dt = datetime.now()
    datetime = dt.strftime("%Y%m%d_%H%M")
    
    #PC Directory
    scrptfolder = os.path.dirname(__file__) #Returns the UNC of the folder where this python file sits
    folder_lst = os.path.split(scrptfolder) #make a list of the head and tail of the scripts folder
    local_root_fld = folder_lst[0] #Access the head (full directory) where the scripts folder resides
    localoutputws = os.path.join(local_root_fld,"Output","Output.gdb")
    scratchworkspace = os.path.join(local_root_fld,"ScratchWorkspace","scratch.gdb")
    scratchfolder = os.path.join(local_root_fld,"ScratchWorkspace")
    rawdatastoragegdb = os.path.join(local_root_fld,"NIFC_DL_RawDataArchive","RawDLArchive.gdb")
    QAQCsourcemetadatapath = os.path.join(local_root_fld,"Metadata","OpsData_QAQC.xml")
    
    # URLs to NIFC data. Update as needed.
    
    # URL to full history WFIGS Wildland Fire Perimeters
    nifc_pbl_fullhistory_url = "https://opendata.arcgis.com/api/v3/datasets/585b8ff97f5c45fe924d3a1221b446c6_0/downloads/data?format=fgdb&spatialRefId=4326"
    # Conditional URLs based on the fire year
    if FireYear == "2017":
        # URL to Operational Data Archive 2017
        nifc_pbl_OpsData_url = "https://opendata.arcgis.com/api/v3/datasets/ebcb160b82a242369caf0b7ed9640ac7_1/downloads/data?format=fgdb&spatialRefId=4326&where=1%3D1"
    if FireYear == "2018":
        # URL to Operational Data Archive 2018
        nifc_pbl_OpsData_url = "https://opendata.arcgis.com/api/v3/datasets/2aa165c74bf040f1a44c63b505f1a940_1/downloads/data?format=fgdb&spatialRefId=4326&where=1%3D1"
    if FireYear == "2019":
        # URL to Operational Data Archive 2019
        nifc_pbl_OpsData_url = "https://opendata.arcgis.com/api/v3/datasets/2827d083ddc14464a8eab3181e8bf13e_0/downloads/data?format=fgdb&spatialRefId=4326&where=1%3D1"
    if FireYear == "2020":
        # URL to Operational Data Archive 2020
        nifc_pbl_OpsData_url = "https://www.arcgis.com/sharing/rest/content/items/ea843f7f091f4c7f9743798b64c864be/data"
    if FireYear == "2021":
        # URL to Operational Data Archive 2021
        nifc_pbl_OpsData_url = "https://www.arcgis.com/sharing/rest/content/items/af727c41d79643b091cee372233110d4/data"
    if FireYear == "2022":
        # URL to Operational Data Archive 2022
        nifc_pbl_OpsData_url = "https://opendata.arcgis.com/api/v3/datasets/696c45c4ecd34948b1ae87d2f567e347_5/downloads/data?format=fgdb&spatialRefId=4326&where=1%3D1"
        
#Hardcoded Inputs used for processing
    USStates = os.path.join(scratchworkspace,"USStates")
    # Set output variable names conditionally based on the DownloadOpsDataTrigger flag and the FireYear
    if DownloadOpsDataTrigger == "true":
        if FireYear in ["2017","2018","2019","2020","2021","2022"]:
            final_Hist_fire_perimeters = "UserInputFirePerims_"+FireName+"_CY"+FireYear+"_"+datetime  
            final_OpsDataArchive = "OpsData_Final_"+FireName+"_CY"+FireYear+"_"+datetime
            QAQCd_OpsData = "OpsData_QAQC_"+FireName+"_CY"+FireYear+"_"+datetime
            RawOpsData = "RawOpsData_CY"+FireYear+"_"+datetime
    if DownloadOpsDataTrigger == "false":
        final_Hist_fire_perimeters = "UserInputFirePerims_"+FireName+"_CY"+UserProvidedFireYear+"_"+datetime  
        final_OpsDataArchive = "OpsData_Final_"+FireName+"_CY"+UserProvidedFireYear+"_"+datetime
        QAQCd_OpsData = "OpsData_QAQC_"+FireName+"_CY"+UserProvidedFireYear+"_"+datetime
        RawOpsData = "RawOpsData_CY"+UserProvidedFireYear+"_"+datetime
    
except:
    arcpy.AddError("Variables could not be set. Exiting...")
    print("Variables could not be set. Exiting...")
    report_error()
    sys.exit()
    
### - Overwrite and environment settings - ###
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

### - Begin Process - ###
# Check if operational data download is triggered and proceed based on the fire year
if DownloadOpsDataTrigger == "true":
    # Download and process the Operational Data Archive for the specified FireYear
    if FireYear in ["2021"]: 
        try:
            print("Downloading Operational Data Archive "+FireYear)
            arcpy.AddMessage("Downloading Operational Data Archive "+FireYear)
            temparchzip = os.path.join(scratchfolder,"NIFC_"+FireYear+"_OpsDataArchive_"+datetime+".zip")
            dwnld_unzip_filter(nifc_pbl_OpsData_url,temparchzip,"Event_Line_"+FireYear,localoutputws)
            NIFC_OpsDataArchive = os.path.join(localoutputws,"Event_Line_"+FireYear)
            # Announce Completion and final feature class name:
            arcpy.AddMessage("The downloaded NIFC Operational Data is located in: "+localoutputws+" and is named: "+final_OpsDataArchive)
            print("The downloaded NIFC Operational Data is located in: "+localoutputws+" and is named: "+final_OpsDataArchive)
        except:
            arcpy.AddError("Error downloading and unzipping the Operational Data Archive "+FireYear+". Check URL. Exiting.")
            print("Error downloading and unzipping the Operational Data Archive "+FireYear+". Check URL. Exiting.")
            report_error()
            sys.exit()
    #Download the Operational data for 2020 from NIFS
    if FireYear in ["2020"]: 
        try:
            print("Downloading Operational Data Archive "+FireYear)
            arcpy.AddMessage("Downloading Operational Data Archive "+FireYear)
            temparchzip = os.path.join(scratchfolder,"NIFC_"+FireYear+"_OpsDataArchive_"+datetime+".zip")
            dwnld_unzip_filter(nifc_pbl_OpsData_url,temparchzip,"EventLine",localoutputws)
            NIFC_OpsDataArchive = os.path.join(localoutputws,"EventLine")
            # Announce Completion and final feature class name:
            arcpy.AddMessage("The downloaded NIFC Operational Data is located in: "+localoutputws+" and is named: "+final_OpsDataArchive)
            print("The downloaded NIFC Operational Data is located in: "+localoutputws+" and is named: "+final_OpsDataArchive)
        except:
            arcpy.AddError("Error downloading and unzipping the Operational Data Archive "+FireYear+". Check URL. Exiting.")
            print("Error downloading and unzipping the Operational Data Archive "+FireYear+". Check URL. Exiting.")
            report_error()
            sys.exit()
    # Download the Operational data for 2018, 2019, and 2022 from NIFS. This is seperate from 2020 and 2021 as the name is formatted differently at the source (has extra underscores)
    if FireYear in ["2017","2018","2019","2022"]:
        try:
            print("Downloading Operational Data Archive "+FireYear)
            arcpy.AddMessage("Downloading Operational Data Archive "+FireYear)
            temparchzip = os.path.join(scratchfolder,"NIFC_"+FireYear+"_OpsDataArchive_"+datetime+".zip")
            dwnld_unzip_filter(nifc_pbl_OpsData_url,temparchzip,"EventLine"+FireYear,localoutputws)
            NIFC_OpsDataArchive = os.path.join(localoutputws,"EventLine"+FireYear)
            # Announce Completion and final feature class name:
            arcpy.AddMessage("The downloaded NIFC Operational Data is located in: "+localoutputws+" and is named: "+final_OpsDataArchive)
            print("The downloaded NIFC Operational Data is located in: "+localoutputws+" and is named: "+final_OpsDataArchive)
        except:
            arcpy.AddError("Error downloading and unzipping the Operational Data Archive "+FireYear+". Check URL. Exiting.")
            print("Error downloading and unzipping the Operational Data Archive "+FireYear+". Check URL. Exiting.")
            report_error()
            sys.exit()
    # Validate that the FireYear is available for processing, exit if not
    if FireYear not in ["2017","2018","2019","2020","2021","2022"]:
            arcpy.AddError("Specified year for ops data not available. Exiting.")
            print("Specified year for ops data not available. Exiting.")
            report_error()
            sys.exit()

# If download trigger is false, use the user-provided fire year for further processing
if DownloadOpsDataTrigger == "false":
    FireYear = UserProvidedFireYear
'''This section of code...
Filters histiric fire perimeters on user selected calendar year (based on Fire Discovery Time)
Filters operational data based on featureCategory (otherwise interpreted as status) that has been attributed as "completed".
It also filters ops data to only the line types of interest as well as removes features labled as "delete this"
This is done before projecting and repairing geometry as it is not spatially tied, to save time.'''
try:
    arcpy.AddMessage("Filtering NIFS Data Based on Attribution")
    print("Filtering NIFS Data Based on Attribution")
    # Perimeter Data
    # Filtering data based on user-selected year and other attributes
    arcpy.management.MakeFeatureLayer(Hist_fire_perimeters,"Perimeters_"+FireYear, "attr_FireDiscoveryDateTime >= timestamp '"+FireYear+"-01-01 00:00:00' And attr_FireDiscoveryDateTime <= timestamp '"+FireYear+"-12-31 23:59:59'")
    result = arcpy.GetCount_management("Perimeters_"+FireYear)
    count = int(result.getOutput(0))
    if count == 0:
        arcpy.AddMessage("No fire perimeters found. Will not continue")
        print("No fire perimeters found. Will not continue")
        sys.exit()
    arcpy.management.CopyFeatures("Perimeters_"+FireYear, "HistFirePerims_"+FireYear)
    #OPS Data
    # Filter operational data by feature category and remove entries marked for deletion
    #Keep a time stamped copy of the raw data so user can compare processed vs unprocessed data
    arcpy.management.CopyFeatures(NIFC_OpsDataArchive,os.path.join(rawdatastoragegdb,RawOpsData))
    #Filter ops data based on feature category field
    arcpy.management.MakeFeatureLayer(NIFC_OpsDataArchive,"OpsDataArchive_fltr", "FeatureCategory IN ('Completed Burnout', 'Completed Dozer Line', 'Completed Fuel Break', 'Completed Hand Line', 'Completed Mixed Construction Line', 'Completed Plow Line', 'Completed Road as Line', 'Road as Completed Line')",)
    arcpy.management.CopyFeatures("OpsDataArchive_fltr", "OpsDataArchive_Complt")
    #Filter ops data based on delete field
    arcpy.management.MakeFeatureLayer("OpsDataArchive_Complt", "OpsDataArchive_deletethis", "DeleteThis IN ('Yes', 'Yes - Editing Mistake', 'Yes - No Longer Needed')")
    #arcpy.management.MakeFeatureLayer("OpsDataArchive_Complt", "OpsDataArchive_deletethis", "DeleteThis IN ('Yes - Editing Mistake', 'Yes - No Longer Needed') Or FeatureStatus IN ('Proposed') Or FeatureStatus IS NULL")
    arcpy.management.DeleteFeatures("OpsDataArchive_deletethis")
    arcpy.management.Delete(NIFC_OpsDataArchive, "FeatureClass")
    
except:
    arcpy.AddError("Error Filtering Data. Exiting.")
    print("Error Filtering Data. Exiting.")
    report_error()
    sys.exit()
'''This section of the code performs data cleaning on attribute fields, particularly for names and IRWIN ID fields,
by removing accidental spaces and ensuring proper formatting of IRWIN IDs with braces.'''
try:
    arcpy.AddMessage("Cleaning NIFS Attribute Data")
    print("Cleaning NIFS Attribute Data")
    #PERIMETERS: Remove unwanted spaces before and after Incident name
    arcpy.management.MakeFeatureLayer("HistFirePerims_"+FireYear, "FirePerims_nameformattingendwith", "attr_IncidentName LIKE '% '", None)
    arcpy.management.CalculateField("FirePerims_nameformattingendwith", "attr_IncidentName", "!attr_IncidentName![:-1]", "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
    arcpy.management.MakeFeatureLayer("HistFirePerims_"+FireYear, "FirePerims_nameformattingstartwith", "attr_IncidentName LIKE ' %'", None)
    arcpy.management.CalculateField("FirePerims_nameformattingstartwith", "attr_IncidentName", "!attr_IncidentName![1:]", "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
    # Check for existence of fields, and perform field calculations to populate missing fields if necessary
    desc = arcpy.Describe("HistFirePerims_"+FireYear)
    flds = desc.fields
    fldin = 'no'
    for fld in flds:
        if fld.name =='poly_IRWINID':
            fldin='yes'
    if fldin == 'no':
        arcpy.management.CalculateField("HistFirePerims_"+FireYear,"poly_IRWINID","!attr_IrwinID!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    desc = arcpy.Describe("HistFirePerims_"+FireYear)
    flds = desc.fields
    fldin = 'no'
    for fld in flds:
        if fld.name =='attr_POOState':
            fldin='yes'
    if fldin == 'no':
        arcpy.analysis.PairwiseIntersect("HistFirePerims_"+FireYear+";"+USStates,"NIFC_WFIGS_Intersect","ALL",None,"INPUT")
        arcpy.management.AddField("NIFC_WFIGS_Intersect","State_Area","DOUBLE",None,None,None,"","NULLABLE","NON_REQUIRED","")
        arcpy.management.CalculateGeometryAttributes("NIFC_WFIGS_Intersect","State_Area AREA_GEODESIC","","SQUARE_METERS",None,"SAME_AS_INPUT")
        arcpy.management.MakeFeatureLayer("NIFC_WFIGS_Intersect","NIFC_WFIGS_Intersect_Layer",'State_Area = (SELECT MAX("State_Area")FROM NIFC_WFIGS_Intersect)')
        arcpy.management.JoinField("HistFirePerims_"+FireYear,"OBJECTID_1","NIFC_WFIGS_Intersect_Layer","FID_HistFirePerims_"+FireYear,"US_POO_State","NOT_USE_FM",None)
        arcpy.management.CalculateField("HistFirePerims_"+FireYear,"attr_POOState","!US_POO_State!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")

    #PERIMETERS: If the attr_IrwinID is null and the poly_irwinID is not null, then grab the IRWIN ID from that field.
    arcpy.management.MakeFeatureLayer("HistFirePerims_"+FireYear, "UserInputFirePerims_blankattrirwin","poly_IRWINID IS NOT NULL And attr_IrwinID IS NULL")
    arcpy.management.CalculateField("UserInputFirePerims_blankattrirwin","attr_IrwinID","!poly_IRWINID!")
    #PERIMETERS: Remove unwanted spaces before and after IRWIN ID
    arcpy.management.MakeFeatureLayer("HistFirePerims_"+FireYear, "HistFirePerims_IRWINendswith", "attr_IrwinID LIKE '% '", None)
    arcpy.management.CalculateField("HistFirePerims_IRWINendswith", "attr_IrwinID", "!attr_IrwinID![:-1]", "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
    arcpy.management.MakeFeatureLayer("HistFirePerims_"+FireYear, "HistFirePerims_IRWINstartswith", "attr_IrwinID LIKE ' %'", None)
    arcpy.management.CalculateField("HistFirePerims_IRWINstartswith", "attr_IrwinID", "!attr_IrwinID![1:]", "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
    #PERIMETERS: Capitalize all Incident names the same way since comparison and Dissolve accounts for differences
    arcpy.management.CalculateField("HistFirePerims_"+FireYear, "attr_IncidentName", "(!attr_IncidentName!).title()", "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
    #Ops Data
    #OPS: Remove unwanted spaces before and after Incident name. The "get count" will figure out if spaces are still present after removing one that need to be deleted.
    arcpy.management.MakeFeatureLayer("OpsDataArchive_Complt", "OpsDataArchive_nameendswith", "IncidentName LIKE '% '", None)
    arcpy.management.CalculateField("OpsDataArchive_nameendswith", "IncidentName", "!IncidentName![:-1]", "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
    result = arcpy.GetCount_management("OpsDataArchive_nameendswith")
    count = int(result.getOutput(0))
    if count > 0:
        arcpy.management.CalculateField("OpsDataArchive_nameendswith", "IncidentName", "!IncidentName![:-1]", "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
    arcpy.management.MakeFeatureLayer("OpsDataArchive_Complt", "OpsDataArchive_namebeginswith", "IncidentName LIKE ' %'", None)
    arcpy.management.CalculateField("OpsDataArchive_namebeginswith", "IncidentName", "!IncidentName![1:]", "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
    result = arcpy.GetCount_management("OpsDataArchive_namebeginswith")
    count = int(result.getOutput(0))
    if count > 0:
        arcpy.management.CalculateField("OpsDataArchive_namebeginswith", "IncidentName", "!IncidentName![1:]", "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
    #Capitalize all Incident names the same way since comparison accounts for case differences
    arcpy.management.CalculateField("OpsDataArchive_Complt", "IncidentName", "(!IncidentName!).title()", "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
    #Capitalize everything in the IRWIN ID field as later comparisons are case sensitive.
    arcpy.management.CalculateField("OpsDataArchive_Complt","IRWINID","!IRWINID!.upper()","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    #Remove unwanted spaces before and after IRWIN ID. This is more thorough than IncName as more errors were seen here.
    arcpy.management.MakeFeatureLayer("OpsDataArchive_Complt", "OpsData_irwinbeginswith", "IRWINID LIKE ' %'", None)
    arcpy.management.CalculateField("OpsData_irwinbeginswith", "IRWINID", "!IRWINID![1:]", "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
    result = arcpy.GetCount_management("OpsData_irwinbeginswith")
    count = int(result.getOutput(0))
    if count > 0:
        arcpy.management.CalculateField("OpsData_irwinbeginswith", "IRWINID", "!IRWINID![1:]", "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
    result = arcpy.GetCount_management("OpsData_irwinbeginswith")
    count = int(result.getOutput(0))
    if count > 0:
        arcpy.management.CalculateField("OpsData_irwinbeginswith", "IRWINID", "!IRWINID![1:]", "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
    #after IRWIN ID
    arcpy.management.MakeFeatureLayer("OpsDataArchive_Complt", "OpsData_irwinendswith", "IRWINID LIKE '% '", None)
    arcpy.management.CalculateField("OpsData_irwinendswith", "IRWINID", "!IRWINID![:-1]", "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
    result = arcpy.GetCount_management("OpsData_irwinendswith")
    count = int(result.getOutput(0))
    if count > 0:
        arcpy.management.CalculateField("OpsData_irwinendswith", "IRWINID", "!IRWINID![:-1]", "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
    result = arcpy.GetCount_management("OpsData_irwinendswith")
    count = int(result.getOutput(0))
    if count > 0:
        arcpy.management.CalculateField("OpsData_irwinendswith", "IRWINID", "!IRWINID![:-1]", "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
    #Clean up Ops irwin ID field to acount for missing brackets
    arcpy.management.AddField("OpsDataArchive_Complt", "EditedOPS_IRWINID", "TEXT", None, None, None, None, "NULLABLE", "NON_REQUIRED", None)
    arcpy.management.CalculateField("OpsDataArchive_Complt", "EditedOPS_IRWINID", "reclass(!IRWINID!)", "PYTHON3", """def reclass(IRWINID):
        if IRWINID is None:
            return None
        elif not IRWINID.startswith("{"):
            return "{" + IRWINID + "}"
        else:
            return IRWINID""", "TEXT", "NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateField("OpsDataArchive_Complt", "IRWINID", "!EditedOPS_IRWINID!", "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
    arcpy.management.DeleteField("OpsDataArchive_Complt", "EditedOPS_IRWINID")
    #If IRWIN ID does not meet string character threshold then set to NULL. This erases the "uh", "what", and other invalid IRWIN IDS.
    arcpy.management.MakeFeatureLayer("OpsDataArchive_Complt", "OpsDataArchive_IRWINCharlength", 'CHAR_LENGTH("IRWINID") < 36 OR CHAR_LENGTH("IRWINID") > 40', None)
    arcpy.management.CalculateField("OpsDataArchive_IRWINCharlength", "IRWINID", "None", "PYTHON3", '', "TEXT", "NO_ENFORCE_DOMAINS")
except:
    arcpy.AddError("Error creating subset of ops and fire perimeter data. Exiting.")
    print("Error creating subset of ops and fire perimeter data. Exiting.")
    report_error()
    sys.exit()

# This section of the code adds a field to operational data to assign a priority ranking based on the feature category.
try:
    arcpy.AddMessage("Adding Field to Rank Fireline Prioritization")
    print("Adding Field to Rank Fireline Prioritization")
    arcpy.management.AddField("OpsDataArchive_Complt","FirelineCatPrioritizationAsgn","LONG",None,None,None,"","NULLABLE","NON_REQUIRED","")
    # Calculate the prioritization weight based on the FeatureCategory using a defined reclassification function
    arcpy.management.CalculateField("OpsDataArchive_Complt","FirelineCatPrioritizationAsgn","Reclass(!FeatureCategory!)","PYTHON3",
    """def Reclass(FeatureCategory):
    if FeatureCategory =='Completed Road as Line':
        return 1
    elif FeatureCategory =='Road as Completed Line':
        return 1
    elif FeatureCategory =='Completed Dozer Line':
        return 2
    elif FeatureCategory =='Completed Hand Line':
        return 3
    elif FeatureCategory =='Completed Mixed Construction Line':
        return 4
    elif FeatureCategory =='Completed Fuel Break':
        return 5
    elif FeatureCategory =='Completed Burnout':
        return 6
    elif FeatureCategory =='Completed Plow Line':
        return 7
    elif FeatureCategory is None:
        return None
    else: 
        return 1000""","TEXT","NO_ENFORCE_DOMAINS")    
except:
    arcpy.AddError("Error adding field to attribute fireline prioritization. Exiting.")
    print("Error adding field to attribute fireline prioritization. Exiting.")
    report_error()
    sys.exit()

# This part of the script prepares the fire data by projecting it to a standard coordinate system and repairing any geometry issues.
try:
    arcpy.AddMessage("Preprocessing Fire Data")
    print("Preprocessing Fire data")
    #Project Perimeters if needed
    fireperimproj = arcpy.Describe("HistFirePerims_"+FireYear).SpatialReference.factoryCode
    if fireperimproj != 4326:
        print ("Changing Projection of Perimeters to GCS_WGS_1984")
        arcpy.AddMessage("Changing Projection of Perimeters to GCS_WGS_1984")
        arcpy.management.Project("HistFirePerims_"+FireYear,final_Hist_fire_perimeters, arcpy.SpatialReference(4326))
    else:
        arcpy.management.CopyFeatures("HistFirePerims_"+FireYear,final_Hist_fire_perimeters)
    #Project Ops data if needed
    opsdataproj = arcpy.Describe("OpsDataArchive_Complt").SpatialReference.factoryCode
    if opsdataproj != 4326:
        print ("Changing Projection of Ops Data to GCS_WGS_1984")
        arcpy.AddMessage("Changing Projection of Ops Data to GCS_WGS_1984")
        arcpy.management.Project("OpsDataArchive_Complt",final_OpsDataArchive, arcpy.SpatialReference(4326))
    else:
        arcpy.management.CopyFeatures("OpsDataArchive_Complt",final_OpsDataArchive)
    arcpy.management.Delete("HistFirePerims_"+FireYear, "FeatureClass")

    ################Comment this line out if you want all filtered firelines for the year################
    arcpy.management.Delete("OpsDataArchive_Complt", "FeatureClass")
    
    #Repair Geometry and deletes null geometry features
    arcpy.RepairGeometry_management(final_Hist_fire_perimeters,"DELETE_NULL")
    arcpy.RepairGeometry_management(final_OpsDataArchive,"DELETE_NULL")
    #Add new field to calculate geodesic acreage for filtering
    arcpy.management.AddField(final_Hist_fire_perimeters, "Geodesic_Acreage", "DOUBLE", None, None, None, None, "NULLABLE", "NON_REQUIRED", None)
    arcpy.management.CalculateField(final_Hist_fire_perimeters, "Geodesic_Acreage", "!shape.geodesicArea@acres!", "PYTHON_9.3", None)
    #Announce Completion and final feature class name:
    arcpy.AddMessage("Preprocessing: Repairing Geometry and Projecting data completed")
    print("Preprocessing: Repairing Geometry and Projecting data completed")
except:
    arcpy.AddError("Error Preprocessing the NIFC data. Exiting.")
    print("Error Preprocessing the NIFC data. Exiting.")
    report_error()
    sys.exit()

#This section compares IRWIN IDs, Incident name, and POO (point of Orig) of perimeters and firelines.
#This is done to grab all lines outside of buffer area if they have the same IRWIN ID and/or attribute them to the fire if they have the same incident name within the same POO state
try:
    arcpy.management.CopyFeatures(final_Hist_fire_perimeters,(os.path.join(scratchworkspace,"FirePerimsForQuery")))
    queryperims = os.path.join(scratchworkspace,"FirePerimsForQuery")
    #Adds field to track Object ID for query table join when comparing attributes later
    arcpy.management.AddField(final_OpsDataArchive,"OrigOID_Link","TEXT",)
    arcpy.management.CalculateField(final_OpsDataArchive,"OrigOID_Link","!OBJECTID!",)
    #Intersect with States in order to ID lines that have the same name as the perimeter that fall within the same state.
    arcpy.analysis.PairwiseIntersect(final_OpsDataArchive+";"+USStates,(os.path.join(scratchworkspace,"OpsLineStatesInt")))
    # Create a query table for joining features based on multiple fields
    opsstateint = os.path.join(scratchworkspace,"OpsLineStatesInt")
    queryperims = os.path.join(scratchworkspace,"FirePerimsForQuery")
    arcpy.management.MakeQueryTable(queryperims+";"+opsstateint,"Qrytbl","USE_KEY_FIELDS",None,
    in_field="OpsLineStatesInt.IRWINID #;OpsLineStatesInt.OrigOID_Link #;OpsLineStatesInt.US_POO_State #;OpsLineStatesInt.IncidentName #;FirePerimsForQuery.attr_IrwinID #;FirePerimsForQuery.attr_IncidentName #;FirePerimsForQuery.attr_POOState #",
    where_clause="FirePerimsForQuery.attr_IrwinID = OpsLineStatesInt.IRWINID Or FirePerimsForQuery.attr_IncidentName = OpsLineStatesInt.IncidentName And FirePerimsForQuery.attr_POOState = OpsLineStatesInt.US_POO_State")
    #Export table for processing
    arcpy.conversion.ExportTable("Qrytbl","Qrytbl_expt")
    #Add field to hold comparison notes
    arcpy.management.AddField("Qrytbl_expt","QueryComparison","TEXT")
    #conditionally fill comparison field
    arcpy.management.CalculateField("Qrytbl_expt","QueryComparison",
        expression="Reclass(!IRWINID!,!IncidentName!,!attr_IrwinID!,!attr_IncidentName!,!US_POO_State!,!attr_POOState!)",
        expression_type="PYTHON3",
        code_block="""def Reclass(IRWINID,IncidentName,attr_IrwinID,attr_IncidentName,US_POO_State,attr_POOState):
        if IRWINID == attr_IrwinID and IncidentName == attr_IncidentName:
            return "Has Matching IRWIN and Name"
        elif IRWINID == attr_IrwinID:
            return "Has Matching IRWIN ID. Name Taken From Matching IRWIN"
        elif IncidentName == attr_IncidentName and US_POO_State == attr_POOState:
            return "Has Matching Inc Name in Same State. IRWIN Taken From Matching Name"
        else: 
            return "None" """)
    #Join back to OG lines
    arcpy.management.JoinField(final_OpsDataArchive,"OrigOID_Link","Qrytbl_expt","OrigOID_Link","QueryComparison;attr_IrwinID;attr_IncidentName","NOT_USE_FM",None)
    #Populate Fields accordingly
    #Create a field to hold old overwritten IRWIN IDs
    arcpy.management.AddField(final_OpsDataArchive,"OldIRWIN",field_type="TEXT")
    arcpy.management.MakeFeatureLayer(final_OpsDataArchive,"Irwintrackinglayer","QueryComparison = 'Has Matching Inc Name in Same State. IRWIN Taken From Matching Name' And IRWINID IS NOT NULL")
    arcpy.management.CalculateField("Irwintrackinglayer","OldIRWIN","!IRWINID!")
    arcpy.management.MakeFeatureLayer(final_OpsDataArchive,"Irwinchange","QueryComparison = 'Has Matching Inc Name in Same State. IRWIN Taken From Matching Name'")
    arcpy.management.CalculateField("Irwinchange","IRWINID","!attr_IrwinID!")
    #Attribute names correctly based off perimeter attributes
    arcpy.management.AddField(final_OpsDataArchive,"OldName","TEXT")
    arcpy.management.MakeFeatureLayer(final_OpsDataArchive,"Nametrackingchange","QueryComparison = 'Has Matching IRWIN ID. Name Taken From Matching IRWIN' And IncidentName IS NOT NULL",)
    arcpy.management.CalculateField("Nametrackingchange","OldName","!IncidentName!")
    arcpy.management.MakeFeatureLayer(final_OpsDataArchive,"Namechange","QueryComparison = 'Has Matching IRWIN ID. Name Taken From Matching IRWIN'")
    arcpy.management.CalculateField("Namechange","IncidentName","!attr_IncidentName!")
    #Clean up workspace and features
    arcpy.management.Delete((os.path.join(scratchworkspace,"FirePerimsForQuery")), "FeatureClass")
    arcpy.management.Delete((os.path.join(scratchworkspace,"OpsLineStatesInt")), "FeatureClass")
    arcpy.management.Delete("Qrytbl_expt")
    arcpy.management.DeleteField(final_OpsDataArchive,"attr_IrwinID;attr_IncidentName","DELETE_FIELDS")
except:
    arcpy.AddError("Error Comparing Attributes. Exiting.")
    print("Error Comparing Attributes. Exiting.")
    report_error()
    sys.exit()

#At this point all features regardless of buffer/location have been selected if name (within state) or IRWIN match.
# This section applies quality control to fire operations data based on proximity to fire perimeters.
# It ensures that features are correctly attributed even if they don't have matching names or IRWIN IDs but are within a buffer of a fire perimeter.
try:
    #Select data that was not identified as part of the fire through attribution
    arcpy.management.MakeFeatureLayer(final_OpsDataArchive,"OpsData_comparison_attr","QueryComparison IS NOT NULL")
    # Export identified features and remove them from the buffer selection process
    arcpy.conversion.ExportFeatures("OpsData_comparison_attr","OpsData_attrcompare")
    arcpy.management.DeleteFeatures("OpsData_comparison_attr")
    arcpy.AddMessage("Buffering Fire Perimeters to Select FireLines to be Included That Don't Have Matching Attribution")
    print("Buffering Fire Perimeters to Select FireLines to be Included That Don't Have Matching Attribution")
    # Buffer the fire perimeters
    arcpy.analysis.PairwiseBuffer(final_Hist_fire_perimeters,"FirePerimsBuffer",PerimBufferIntersect+" Meters","NONE",None,"GEODESIC","0 DecimalDegrees")
    # Remove features outside of the buffer
    arcpy.management.MakeFeatureLayer(final_OpsDataArchive, "OpsDataArchive_layerforNo")
    arcpy.management.SelectLayerByLocation("OpsDataArchive_layerforNo", "INTERSECT", "FirePerimsBuffer", None, "NEW_SELECTION", "INVERT")
    arcpy.management.DeleteFeatures("OpsDataArchive_layerforNo")
    #Grab the largest fire of the user provided perimeters (complex) to then attribute IRWIN ID and Inc Name to the firelines that reside within the buffer area
    arcpy.management.MakeTableView(final_Hist_fire_perimeters,"UserInputFirePerims","Geodesic_Acreage = (SELECT MAX(Geodesic_Acreage) FROM "+final_Hist_fire_perimeters+")")
    arcpy.conversion.ExportTable("UserInputFirePerims","LrgestFireAcrg_ForNamingFL")
    #Create a common field in both feature classes for the attributes to join on
    arcpy.management.CalculateField("LrgestFireAcrg_ForNamingFL","Flag",'"Name and IRWIN taken from largest perim. Did not have matching attributes but intersected buffer."',"PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateField(final_OpsDataArchive,"Flag",'"Name and IRWIN taken from largest perim. Did not have matching attributes but intersected buffer."',"PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.JoinField(final_OpsDataArchive,"Flag","LrgestFireAcrg_ForNamingFL","Flag","attr_IncidentName;attr_IrwinID","NOT_USE_FM",None)
    #Populate QueryComparison notes field based on IRWIN and Inc Name
    arcpy.management.CalculateField(final_OpsDataArchive,"QueryComparison","Reclass(!QueryComparison!,!IncidentName!,!IRWINID!)","PYTHON3",
        """def Reclass(QueryComparison,IncidentName,IRWINID):
        if (IncidentName is None and IRWINID is None):
            return "Within Buffer but Both Inc Name and IRWIN Null. Both Changed to Match Largest Perim"
        elif (IRWINID is None and IncidentName is not None):
            return "Within Buffer but IRWIN Null. Both Changed to Match Largest Perim"
        elif (IRWINID is not None and IncidentName is None):
            return "Within Buffer but Inc Name Null. Both Changed to Match Largest Perim"
        elif (IRWINID is not None and IncidentName is not None):
            return "Within Buffer but Both Inc Name and IRWIN Didnt Match. Both Changed to Match Largest Perim"
        else: 
            return "Did not match query. Error." """)
    #Populate fields accordingly
    #Both Null
    arcpy.management.MakeFeatureLayer(final_OpsDataArchive,"OpsData_BothNull","QueryComparison = 'Within Buffer but Both Inc Name and IRWIN Null. Both Changed to Match Largest Perim'")
    arcpy.management.CalculateField("OpsData_BothNull","IRWINID","!attr_IrwinID!")
    arcpy.management.CalculateField("OpsData_BothNull","IncidentName","!attr_IncidentName!")
    #IRWIN Null
    arcpy.management.MakeFeatureLayer(final_OpsDataArchive,"OpsData_irwinNull","QueryComparison = 'Within Buffer but IRWIN Null. Both Changed to Match Largest Perim'")
    arcpy.management.CalculateField("OpsData_irwinNull","OldName","!IncidentName!")
    arcpy.management.CalculateField("OpsData_irwinNull","IncidentName","!attr_IncidentName!")
    arcpy.management.CalculateField("OpsData_irwinNull","IRWINID","!attr_IrwinID!")
    #Inc Name Null
    arcpy.management.MakeFeatureLayer(final_OpsDataArchive,"OpsData_nameNull","QueryComparison = 'Within Buffer but Inc Name Null. Both Changed to Match Largest Perim'")
    arcpy.management.CalculateField("OpsData_nameNull","OldIRWIN","!IRWINID!")
    arcpy.management.CalculateField("OpsData_nameNull","IncidentName","!attr_IncidentName!")
    arcpy.management.CalculateField("OpsData_nameNull","IRWINID","!attr_IrwinID!")
    #Both didnt match
    arcpy.management.MakeFeatureLayer(final_OpsDataArchive,"OpsData_nomatch","QueryComparison = 'Within Buffer but Both Inc Name and IRWIN Didnt Match. Both Changed to Match Largest Perim'")
    arcpy.management.CalculateField("OpsData_nomatch","OldIRWIN","!IRWINID!")
    arcpy.management.CalculateField("OpsData_nomatch","OldName","!IncidentName!")
    arcpy.management.CalculateField("OpsData_nomatch","IncidentName","!attr_IncidentName!")
    arcpy.management.CalculateField("OpsData_nomatch","IRWINID","!attr_IrwinID!")
    #this line saves the QAQCed ops data
    arcpy.management.Merge(final_OpsDataArchive+";OpsData_attrcompare",QAQCd_OpsData)
    arcpy.Delete_management(final_OpsDataArchive)
    arcpy.management.DeleteField(QAQCd_OpsData,"OrigOID_Link;Flag;attr_IncidentName;attr_IrwinID","DELETE_FIELDS")
    #Calculate the Line Length in KM to ID potential faulty data
    arcpy.management.CalculateGeometryAttributes(QAQCd_OpsData,"LineLengthGeodesicKM LENGTH_GEODESIC","KILOMETERS","",None,"SAME_AS_INPUT")
    #Keep a copy of the firelines to then rid of duplicates. This copy will not have attribute QAQC tracking fields.
    arcpy.management.CopyFeatures(QAQCd_OpsData,final_OpsDataArchive)
    #Clean up workspace
    fc_Delete = ["FirePerimsBuffer","LrgestFireAcrg_ForNamingFL","OpsData_attrcompare"]
    for fc in fc_Delete:
        fc_path = os.path.join(localoutputws, fc)
        if arcpy.Exists(fc_path):
            arcpy.Delete_management(fc_path)
except:
    arcpy.AddError("Error Buffering Fire Perimeters and QAQCing Ops Data. Exiting.")
    print("Error Buffering Fire Perimeters and QAQCing Ops Data. Exiting.")
    report_error()
    sys.exit()
    
# This part of the script removes duplicates from the operational firelines data based on shape, incident name, line type, and IRWIN ID.
#It has been commented out as firelines need visual inspection and QAQC before proceeding with FLE or other types of analysis.
##try:
##    arcpy.management.DeleteField(final_OpsDataArchive,"MapMethod;RepairStatus;LengthFeet;GlobalID;LineWidthFeet;DeleteThis;FeatureAccess;FeatureStatus;IsVisible;Label;LineDateTime;CreateDate;DateCurrent;ArchClearance;GDB_FROM_DATE;GDB_TO_DATE;QueryComparison;OldIRWIN;OldName;ORIG_FID","DELETE_FIELDS")
##    # Convert multipart firelines to single part for processing
##    arcpy.management.MultipartToSinglepart(final_OpsDataArchive,"SinglepartFirelines")
##    # Identify identical features based on specified attributes
##    arcpy.management.FindIdentical("SinglepartFirelines","FindIdentical","Shape;IncidentName;FeatureCategory;IRWINID;FirelineCatPrioritizationAsgn",xy_tolerance=None,z_tolerance=0,output_record_option="ONLY_DUPLICATES")
##    arcpy.management.JoinField("SinglepartFirelines","OBJECTID","FindIdentical","IN_FID","FEAT_SEQ")
##    # Select and dissolve duplicates based on the join
##    arcpy.management.MakeFeatureLayer("SinglepartFirelines","UserInputFirePerims_dups","FEAT_SEQ IS NOT NULL")
##    arcpy.analysis.PairwiseDissolve("UserInputFirePerims_dups","DupsDisssglpt","IncidentName;FeatureCategory;FirelineCatPrioritizationAsgn;IRWINID;FEAT_SEQ",None,"SINGLE_PART","")
##    # Remove the original duplicates from the dataset
##    arcpy.management.DeleteFeatures("UserInputFirePerims_dups")
##    # Handle potential issues with the Find Identical tool by repeating the process
##    arcpy.management.DeleteField("DupsDisssglpt","FEAT_SEQ","DELETE_FIELDS")
##    arcpy.management.FindIdentical("DupsDisssglpt","Dups_findIdent2",fields="Shape;IncidentName;FeatureCategory;IRWINID;FirelineCatPrioritizationAsgn",xy_tolerance="0 Meters",z_tolerance=0,output_record_option="ONLY_DUPLICATES")
##    arcpy.management.JoinField(in_data="DupsDisssglpt",in_field="OBJECTID",join_table="Dups_findIdent2",join_field="IN_FID",fields="FEAT_SEQ",fm_option="NOT_USE_FM",field_mapping=None)
##    #Dissolve again to rid of identical overlaps.. again
##    arcpy.analysis.PairwiseDissolve("DupsDisssglpt","DupsDiss2","IncidentName;IRWINID;FirelineCatPrioritizationAsgn;FEAT_SEQ;FeatureCategory",None,"SINGLE_PART","")
##    arcpy.Delete_management(final_OpsDataArchive)
##    #Merge final results
##    arcpy.management.Merge("SinglepartFirelines;DupsDiss2","fnlmrg")
##    arcpy.analysis.PairwiseDissolve("fnlmrg",final_OpsDataArchive,"IRWINID;IncidentName;FeatureCategory;FirelineCatPrioritizationAsgn",None,"MULTI_PART","")
##    #Clean up workspace
##    fc_Delete = ["SinglepartFirelines","FindIdentical","DupsDisssglpt","Dups_findIdent2","DupsDiss2","fnlmrg"]
##    for fc in fc_Delete:
##        fc_path = os.path.join(localoutputws, fc)
##        if arcpy.Exists(fc_path):
##            arcpy.Delete_management(fc_path)
##except:
##    arcpy.AddError("Error Remove duplicates based on shape and Incident Name, Line Type, and IRWIN ID.... Exiting")
##    print("Error Remove duplicates based on shape and Incident Name, Line Type, and IRWIN ID.... Exiting")
##    report_error()
##    sys.exit()

try:
    print("Writing Metadata to Output Feature Classes")
    arcpy.AddMessage("Writing Metadata to Output Feature Classes")
    tgt_item_md = md.Metadata(QAQCd_OpsData)
    tgt_item_md.importMetadata(QAQCsourcemetadatapath)
    tgt_item_md.save()

##    tgt_item_md = md.Metadata(final_OpsDataArchive)
##    tgt_item_md.importMetadata(QAQCsourcemetadatapath)
##    tgt_item_md.save()
except:
    arcpy.AddError("Error Importing Metadata. Exiting.")
    print("Error Importing Metadata. Exiting.")
    report_error()
    sys.exit()

print("Script Finished Running.")
arcpy.AddMessage("Script Finished Running.")
