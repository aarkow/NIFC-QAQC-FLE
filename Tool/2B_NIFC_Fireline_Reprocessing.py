# -*- coding: utf-8 -*-
"""
Name: 2B NIFC Fireline Reprocessing
Author: Alex Arkowitz @ Colorado State University - alexander.arkowitz@colostate.edu
Date Created: 02/13/2023

Limitations:
Compatible with Python 3.x and ArcGIS Pro environments only which can be a limitation if the script is used in different versions of the software where the tools may have been updated or deprecated.
Assumes input datasets follow standard NIFC schemas.
The script is designed for National Interagency Fire Center specific fire-related datasets, limiting its applicability to other types of spatial analyses without significant modification
There may be hardcoded paths and URLs, which may change over time, thus requiring manual updates to the script.
The processing power required and the need for a stable internet connection also play a role in the tool's performance and capabilities.

Usage: This tool should be used if the user needs a dissolved/simplified version of the QAQC lines after having done manual edits to tool 2 fireline output.
#####It is not necessary for the QAQC process.#####

Description: This script will identify the most common incident name and irwin id in the fireline feature class and attribute it to all firelines. It then removes duplicates based on shape and Incident Name, Line Type, and IRWIN ID.
The resulting firelines are then dissolved to give the user a simplified fireline dataset.

"""
#import libraries
import arcpy, os, sys, requests, traceback
from datetime import datetime, timezone

#User Set Hardcoded parameters from ArcPro Tool
QAQC_Firelines_ToDiss = arcpy.GetParameter(0)  #feature set type input parameter.
IncName = arcpy.GetParameterAsText(1)
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
    
#Output Names - Variables Conditionally Set
    ReprocessedOpsData = "OpsData_QAQC_"+IncName+"_Dislvd_"+datetime
    
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

###-Begin Process-###
'''This next section will find the most common Inc Name and IRWIN IDs and attribute them to all firelines'''
try:
    print("Identifying Most Common Inc Name and IRWIN ID and Attributing Them to All Input Firelines")
    arcpy.AddMessage("Identifying Most Common Inc Name and IRWIN ID and Attributing Them to All Input Firelines")
    arcpy.conversion.ExportFeatures(QAQC_Firelines_ToDiss,"Firelines_OneFireDiss")
    arcpy.analysis.Statistics("Firelines_OneFireDiss","OpsData_Statistics","IncidentName COUNT;IRWINID COUNT","IncidentName;IRWINID","")
    #Exporting table view occasionally gets rid of IRWIN ID unless you copy it. ESRI Bug? Get around this by making new irwin ID field
    arcpy.management.AddField("OpsData_Statistics","IRWIN2","TEXT")
    arcpy.management.CalculateField("OpsData_Statistics","IRWIN2","!IRWINID!")
    #Make table view capturing most common IRWIN and Name
    arcpy.management.MakeTableView("OpsData_Statistics","OpsData_Statistics_View","COUNT_IncidentName = (SELECT MAX(COUNT_IncidentName) FROM OpsData_Statistics) AND COUNT_IRWINID = (SELECT MAX(COUNT_IRWINID) FROM OpsData_Statistics)")
    #Export table view
    arcpy.conversion.ExportTable("OpsData_Statistics_View","OpsData_Stats_MstCmn")
    #Create fields to join data
    arcpy.management.AddField("OpsData_Stats_MstCmn","CommonJoin","LONG")
    arcpy.management.AddField("Firelines_OneFireDiss","CommonJoin","LONG")
    arcpy.management.CalculateField("Firelines_OneFireDiss","CommonJoin","1")
    arcpy.management.CalculateField("OpsData_Stats_MstCmn","CommonJoin","1")
    arcpy.management.DeleteField("Firelines_OneFireDiss","IncidentName;IRWINID","DELETE_FIELDS")
    arcpy.management.JoinField("Firelines_OneFireDiss","CommonJoin","OpsData_Stats_MstCmn","CommonJoin","IRWINID;IncidentName","NOT_USE_FM",None)
    arcpy.management.Delete("OpsData_Stats_MstCmn")
    arcpy.management.DeleteField("Firelines_OneFireDiss","CommonJoin","DELETE_FIELDS")
except:
    arcpy.AddError("Error Attributing Inc and IRWIN to Firelines... Exiting")
    print("Error Attributing Inc and IRWIN to Firelines... Exiting")
    report_error()
    sys.exit()

try:
    #Remove duplicates based on shape and Incident Name, Line Type, and IRWIN ID.
    arcpy.management.MultipartToSinglepart("Firelines_OneFireDiss","SinglepartFirelines2")
    arcpy.management.FindIdentical("SinglepartFirelines2","FindIdentical2","Shape;IncidentName;FeatureCategory;IRWINID;FirelineCatPrioritizationAsgn",xy_tolerance=None,z_tolerance=0,output_record_option="ONLY_DUPLICATES")
    arcpy.management.JoinField("SinglepartFirelines2","OBJECTID","FindIdentical2","IN_FID","FEAT_SEQ")
    #Select only features that were identified to have identical features.
    arcpy.management.MakeFeatureLayer("SinglepartFirelines2","UserInputFireline_dups","FEAT_SEQ IS NOT NULL")
    #Dissolve features that were duplicates
    arcpy.analysis.PairwiseDissolve("UserInputFireline_dups","DupsDisssglpt2","IncidentName;FeatureCategory;FirelineCatPrioritizationAsgn;IRWINID;FEAT_SEQ",None,"SINGLE_PART","")
    #Delete features that were dissolved from fireline data.
    arcpy.management.DeleteFeatures("UserInputFireline_dups")
    #Several Identicals still found due to issues with Find Identical Tool. Delete Feat Seq field and rerun
    arcpy.management.DeleteField("DupsDisssglpt2","FEAT_SEQ","DELETE_FIELDS")
    arcpy.management.FindIdentical("DupsDisssglpt2","Dups_findIdent2",fields="Shape;IncidentName;FeatureCategory;IRWINID;FirelineCatPrioritizationAsgn",xy_tolerance="0 Meters",z_tolerance=0,output_record_option="ONLY_DUPLICATES")
    arcpy.management.JoinField(in_data="DupsDisssglpt2",in_field="OBJECTID",join_table="Dups_findIdent2",join_field="IN_FID",fields="FEAT_SEQ",fm_option="NOT_USE_FM",field_mapping=None)
    #Dissolve again to rid of identical overlaps.. again
    arcpy.analysis.PairwiseDissolve("DupsDisssglpt2","DupsDissrnd2","IncidentName;IRWINID;FirelineCatPrioritizationAsgn;FEAT_SEQ;FeatureCategory",None,"SINGLE_PART","")
    arcpy.Delete_management("Firelines_OneFireDiss")
    #Merge final results
    arcpy.management.Merge("SinglepartFirelines2;DupsDissrnd2","Firelines_OneFireDiss")
    arcpy.management.DeleteField("Firelines_OneFireDiss","ORIG_FID;FEAT_SEQ","DELETE_FIELDS")
    arcpy.analysis.PairwiseDissolve("Firelines_OneFireDiss",ReprocessedOpsData,"IRWINID;IncidentName;FeatureCategory;FirelineCatPrioritizationAsgn",None,"MULTI_PART","")
    #Clean up workspace
    fc_Delete = ["OpsData_Statistics","SinglepartFirelines2","FindIdentical2","DupsDisssglpt2","Dups_findIdent2","DupsDissrnd2","Firelines_OneFireDiss"]
    for fc in fc_Delete:
        fc_path = os.path.join(localoutputws, fc)
        if arcpy.Exists(fc_path):
            arcpy.Delete_management(fc_path)
except:
    arcpy.AddError("Error #Remove duplicates based on shape and Incident Name, Line Type, and IRWIN ID.... Exiting")
    print("Error #Remove duplicates based on shape and Incident Name, Line Type, and IRWIN ID.... Exiting")
    report_error()
    sys.exit()

    
print("Script Finished Running.")
arcpy.AddMessage("Script Finished Running.")
