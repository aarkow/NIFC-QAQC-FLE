# -*- coding: utf-8 -*-
"""
Name: WFIGS NIFC Fire Perimeter and Fireline Processing and QAQC
Author: Alex Arkowitz @ Colorado State University - alexander.arkowitz@colostate.edu
Date Created: 11/07/2023

Limitations:
Compatible with Python 3.x and ArcGIS Pro environments only which can be a limitation if the script is used in different versions of the software where the tools may have been updated or deprecated.
Assumes input datasets follow standard NIFC schemas.
The script is designed for National Interagency Fire Center specific fire-related datasets, limiting its applicability to other types of spatial analyses without significant modification
The processing power required play a role in the tool's performance and capabilities.

Usage: This tool should be used when engagement attributes need to be attributed to QAQCed firelines, or when the user requires a buffered fireline output without overlapping features, suitable for overlay analysis.
1. Ensure input datasets are properly formatted according to NIFC guidelines.
2. Execute as a script tool in ArcGIS Pro with the required parameters.
3. Can be automated as part of larger geoprocessing workflows.

Description:
This tool integrates NIFC Wildfire perimeter and QAQCed fireline datasets to produce two types of geospatial products:
1. A line feature class that attributes engagement status to firelines relative to the fire perimeter.
2. A polygon feature class representing buffered firelines, suitable for overlay analysis, which includes attributes indicating types of firelines and a cumulative rank of treatment efforts.
The user will provide QAQCed firelines, a perimeter, an engagement (distance from perimeter) to identify held line, and a buffer size for the overlay polygon output.
The tool will first identify if the user has input a complex (multiple fire perimeters) and attribute them all based on the largest perimeter's attributes.
It will then attribute fireline engagement based on the user input fireline engagement buffer area.
"""
#import libraries
import arcpy, os, urllib, sys, requests, traceback
from zipfile import ZipFile
from sys import argv
from datetime import datetime, timezone

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
    inputsws = os.path.join(local_root_fld,"Inputs","InputGeodatabase.gdb")
    rawdatastoragegdb = os.path.join(local_root_fld,"NIFC_DL_RawDataArchive","RawDLArchive.gdb")
    FLEsourcemetadatapath = os.path.join(local_root_fld,"Metadata","FLE_Metrics.xml")
    
    #User Set Hardcoded parameters from ArcPro Tool
    QAQCed_Firelines = arcpy.GetParameter(0)#feature set type input parameter.
    Perimeters = arcpy.GetParameter(1)#feature set type input parameter.
    FLEngageOutputName = arcpy.GetParameterAsText(2)#Name of final attributed firelines
    FirelineEngagmentBuffer = arcpy.GetParameter(3) #Distance From Perimeter that line will be considered "held"
    FirelineBuffer = arcpy.GetParameter(4) #Size of fireline buffer for second output feature class
    
    #Format the buffer list parameter for mutiple ring buffer tool input
    FirelineEngagmentBuffList = [-FirelineEngagmentBuffer,FirelineEngagmentBuffer]
    
    #Format user provided Output Name to have datetime appended
    FLEngageOutput = "LineEngagement_"+FLEngageOutputName+"_"+datetime
    IncidentName_BuffEnggmntLines_Datetime = "LineEngmntOvrly_"+FLEngageOutputName+"_"+(str(FirelineEngagmentBuffer))+"MtrBuff_"+datetime


except:
    arcpy.AddError("Variables could not be set. Exiting...")
    print("Variables could not be set. Exiting...")
    report_error()
    sys.exit()
    
###-Overwrite and environment settings-###
try:
    # To allow overwriting outputs change overwriteOutput option to True.
    arcpy.env.overwriteOutput = True
    # Environment settings
    arcpy.env.scratchWorkspace = scratchworkspace
    arcpy.env.workspace = localoutputws
except:
    arcpy.AddError("Evironments could not be set. Exiting...")
    print("Evironments could not be set. Exiting...")
    report_error()
    sys.exit()

###-Begin Process-###
# This section is responsible for processing multiple perimeters into a single 'complex' feature.
# It also applies the attributes from the largest perimeter (by geodesic area) to all other perimeters.
try:
    result = arcpy.GetCount_management(Perimeters)
    count = int(result.getOutput(0))
    # If there is more than one perimeter, they need to be dissolved into a complex.
    if count > 1:
        arcpy.AddMessage("Dissolving All Perimeters in the Complex and Taking Attribution From the Largest Perimeter")
        print("Dissolving All Perimeters in the Complex and Taking Attribution From the Largest Perimeter")
        arcpy.management.CopyFeatures(Perimeters,"PerimsToDiss")
        #if more than one perim, check if perim as
        lstFields = arcpy.ListFields("PerimstoDiss")
        lstfieldNames = [f.name for f in lstFields]
        # If the 'attr_FireMgmtComplexity' field exists, handle the complex attribution logic. 
        if "attr_FireMgmtComplexity" in lstfieldNames:
            #Team Cmplx Coding. If only one perim in the complex has a FireMgmtCmplx Team, it will be attributed to all. If several do, they will be concatenated.
            arcpy.management.MakeFeatureLayer("PerimsToDiss","Perims_Teams","attr_FireMgmtComplexity IS NOT NULL")
            resultteams = arcpy.GetCount_management("Perims_Teams")
            count2 = int(resultteams.getOutput(0))
            if count2 >= 1:
                if count2 > 1:
                    arcpy.analysis.Statistics("Perims_Teams","Perims_Teams_Statistics","attr_FireMgmtComplexity CONCATENATE",None,"; ")
                if count2 == 1:
                    arcpy.analysis.Statistics("Perims_Teams","Perims_Teams_Statistics","attr_FireMgmtComplexity FIRST",None)
                arcpy.management.AddField("PerimsToDiss","LinkingField","SHORT")
                arcpy.management.AddField("Perims_Teams_Statistics","LinkingField","SHORT")
                arcpy.management.CalculateField("PerimsToDiss","LinkingField","1","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
                arcpy.management.CalculateField("Perims_Teams_Statistics","LinkingField","1","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
                if count2 > 1:
                    arcpy.management.JoinField("PerimsToDiss","LinkingField","Perims_Teams_Statistics","LinkingField","CONCATENATE_attr_FireMgmtComplexity","NOT_USE_FM",None)
                    arcpy.management.DeleteField("PerimsToDiss","attr_FireMgmtComplexity","DELETE_FIELDS")
                    arcpy.management.AddField("PerimsToDiss","attr_FireMgmtComplexity","TEXT",None,None,None,"","NULLABLE","NON_REQUIRED","")
                    arcpy.management.CalculateField("PerimsToDiss","attr_FireMgmtComplexity","!CONCATENATE_attr_FireMgmtComplexity!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
                    arcpy.management.DeleteField("PerimsToDiss","LinkingField;CONCATENATE_attr_FireMgmtComplexity","DELETE_FIELDS")
                if count2 == 1:
                    arcpy.management.JoinField("PerimsToDiss","LinkingField","Perims_Teams_Statistics","LinkingField","FIRST_attr_FireMgmtComplexity","NOT_USE_FM",None)
                    arcpy.management.DeleteField("PerimsToDiss","attr_FireMgmtComplexity","DELETE_FIELDS")
                    arcpy.management.AddField("PerimsToDiss","attr_FireMgmtComplexity","TEXT",None,None,None,"","NULLABLE","NON_REQUIRED","")
                    arcpy.management.CalculateField("PerimsToDiss","attr_FireMgmtComplexity","!FIRST_attr_FireMgmtComplexity!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
                    arcpy.management.DeleteField("PerimsToDiss","LinkingField;FIRST_attr_FireMgmtComplexity","DELETE_FIELDS")
                arcpy.management.Delete("Perims_Teams_Statistics","")
        if "attr_FireMgmtComplexity" not in lstfieldNames:
            arcpy.management.AddField("PerimsToDiss","attr_FireMgmtComplexity","TEXT",None,None,None,"","NULLABLE","NON_REQUIRED","")
        #Make sure geodesic acreage was calculated correctly.
        lstFields = arcpy.ListFields("PerimstoDiss")
        lstfieldNames = [f.name for f in lstFields]
        if "GoedesicAcreage" in lstfieldNames:
            arcpy.management.DeleteField("PerimsToDiss","GeodesicAcreage","DELETE_FIELDS")
        arcpy.management.AddField("PerimstoDiss","GeodesicAcreage","DOUBLE",None,None,None,"","NULLABLE","NON_REQUIRED","")
        arcpy.management.CalculateGeometryAttributes("PerimstoDiss","GeodesicAcreage AREA_GEODESIC","","ACRES",None,"SAME_AS_INPUT")
        arcpy.management.MakeFeatureLayer("PerimsToDiss","Perimeters_Lrgst","GeodesicAcreage = (SELECT MAX(GeodesicAcreage) FROM PerimsToDiss)")
        arcpy.conversion.ExportFeatures("Perimeters_Lrgst","Perimeters_LrgstPerim")
        arcpy.management.CalculateField("Perimeters_LrgstPerim","Joinfield","1")
        arcpy.management.CalculateField("PerimsToDiss","Joinfield","1")
        arcpy.management.DeleteField("PerimsToDiss","attr_IrwinID;attr_IncidentName","DELETE_FIELDS")
        arcpy.management.JoinField("PerimsToDiss","Joinfield","Perimeters_LrgstPerim","Joinfield","attr_IncidentName;attr_IrwinID")
        arcpy.analysis.PairwiseDissolve("PerimsToDiss",Perims,"attr_IncidentName;attr_IrwinID;attr_FireMgmtComplexity",None,"MULTI_PART")
        arcpy.management.CalculateField(Perims,"attr_IncidentName",'!attr_IncidentName!+ " Complex"',"PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    # If only a single perimeter is provided, check for the 'attr_FireMgmtComplexity' field and act accordingly.
    elif count == 1:
        lstFields = arcpy.ListFields(Perimeters)
        lstfieldNames = [f.name for f in lstFields]
        if "attr_FireMgmtComplexity" in lstfieldNames:
            print("Fire Mgmt Cmplx Field Present")
        else:
            arcpy.management.AddField(Perimeters,"attr_FireMgmtComplexity","TEXT",None,None,None,"","NULLABLE","NON_REQUIRED","")
        arcpy.management.CopyFeatures(Perimeters,"Perims")
    # If no perimeters are provided, report an error and exit the script.
    elif count == 0:
        arcpy.AddError("No Features Provided in Perimeter Feature Class... Exiting")
        print("No Features Provided in Perimeter Feature Class... Exiting")
        sys.exit()
    fc_Delete = ["Perimeters_Lrgst","FLE_Output_Dateti_Statistics","Perimeters_LrgstPerim","PerimsToDiss"]
    for fc in fc_Delete:
        fc_path = os.path.join(localoutputws, fc)
        if arcpy.Exists(fc_path):
            arcpy.Delete_management(fc_path)
except:
    arcpy.AddError("Error Dissolving Perimeters in the Complex... Exiting")
    print("Error Dissolving Perimeters in the Complex... Exiting")
    fc_Delete = ["Perims","Perimeters_Lrgst","FLE_Output_Dateti_Statistics","Perimeters_LrgstPerim","PerimsToDiss"]
    for fc in fc_Delete:
        fc_path = os.path.join(localoutputws, fc)
        if arcpy.Exists(fc_path):
            arcpy.Delete_management(fc_path) 
    report_error()
    sys.exit()

try:
    arcpy.AddMessage("Attributing Fireline Engagement Attributes Based on User Input Fireline Engagment Buffer Area")
    print("Attributing Fireline Engagement Attributes Based on User Input Fireline Engagment Buffer Area")
    # Copy the QAQCed firelines to an output feature class to avoid modifying the original data.
    arcpy.management.CopyFeatures(QAQCed_Firelines,FLEngageOutput)
    #Dissolve FL to remove duplicates and only keep the highest ranking treatment for areas with duplicate lines and multiple treatments
    # Add a field to the fireline output to hold engagement status (Held, Not Held, Not Engaged).
    arcpy.management.AddField(FLEngageOutput,"FirelineEngagement","TEXT",None,None,None,"","NULLABLE","NON_REQUIRED","")
    # Use the Multiple Ring Buffer tool to create two buffers: one inside (negative distance) and one outside (positive distance) the fire perimeter.
    # This will help identify areas that are held or not by the firelines.
    arcpy.analysis.MultipleRingBuffer("Perims","FirePerims_RingBuffer",FirelineEngagmentBuffList,"Meters","RingBuffDist","NONE","FULL","GEODESIC")
    #export only larger ring buffer as its own feature class. This will be used to erase the smaller ring buffer to create the "held" area.
    arcpy.management.MakeFeatureLayer("FirePerims_RingBuffer","FirePerims_RingBuffer_100Layer","RingBuffDist = "+(str(FirelineEngagmentBuffer))+"")
    arcpy.conversion.ExportFeatures("FirePerims_RingBuffer_100Layer","FirePerims_heldring")
    #Take the smaller rings and erase the area from the exported larger subset to create held area.
    arcpy.management.MakeFeatureLayer("FirePerims_RingBuffer","FirePerims_RingBuffer_-100lyr","RingBuffDist = -"+(str(FirelineEngagmentBuffer))+"")
    arcpy.analysis.PairwiseErase("FirePerims_heldring","FirePerims_RingBuffer_-100lyr","FirePerimsHeldRing")
    #Clip Ops data with small rings to ID "Not Held" fireline
    arcpy.analysis.PairwiseClip(FLEngageOutput,"FirePerims_RingBuffer_-100lyr","OpsData_NotHeldClip")
    #Clip Ops data with buffer area to ID  "Held" fireline
    arcpy.analysis.PairwiseClip(FLEngageOutput,"FirePerimsHeldRing","OpsData_HeldClip")
    #Erase the original ops data with all the rings to only show "not engaged"
    arcpy.analysis.PairwiseErase(FLEngageOutput,"FirePerims_RingBuffer_100Layer","OpsData_NotEngaged")
    #Calculate field to attribute fireline engagement
    arcpy.management.CalculateField("OpsData_NotHeldClip","FirelineEngagement",'"Not Held"',"PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateField("OpsData_HeldClip","FirelineEngagement",'"Held"',"PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateField("OpsData_NotEngaged","FirelineEngagement",'"Not Engaged"',"PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    #Delete ops data so that name can be used for the merge output as well as other non-needed features.
    arcpy.Delete_management(FLEngageOutput)
    # Merge the clipped and erased features back into a single feature class with attributed engagement status.
    arcpy.management.Merge("OpsData_NotHeldClip;OpsData_HeldClip;OpsData_NotEngaged",FLEngageOutput)
    #Clean up processing data
    fc_Delete = ["Perims","FirePerims_RingBuffer","FirePerims_heldring","FirePerimsHeldRing","OpsData_HeldClip","OpsData_NotEngaged","OpsData_NotHeldClip"]
    for fc in fc_Delete:
        fc_path = os.path.join(localoutputws, fc)
        if arcpy.Exists(fc_path):
            arcpy.Delete_management(fc_path)
except:
    arcpy.AddError("Error Could NOT Attribute Fireline Engagement Attributes")
    print("Error Could NOT Attribute Fireline Engagement Attributes")
    report_error()
    sys.exit()


try:
    # Dissolve the firelines based on the feature category to consolidate overlapping features.
    arcpy.analysis.PairwiseDissolve(FLEngageOutput,"Firelines_Diss","FeatureCategory;FirelineEngagement",None,"MULTI_PART","")
    # Add a new short integer field to hold a numeric value for the type of fireline based on the feature category.
    arcpy.management.AddField("Firelines_Diss","LineTypeValue","SHORT",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.AddField("Firelines_Diss","EngagementValue","SHORT",None,None,None,"","NULLABLE","NON_REQUIRED","")
    # Calculate the LineTypeValue field with a numeric ranking based on predefined categories.
    arcpy.management.CalculateField(
        in_table="Firelines_Diss",
        field="LineTypeValue",
        expression="Reclass(!FeatureCategory!)",
        expression_type="PYTHON3",
        code_block="""def Reclass(FeatureCategory):
        if FeatureCategory =='Completed Road as Line':
            return 7
        elif FeatureCategory =='Road as Completed Line':
            return 7
        elif FeatureCategory =='Completed Dozer Line':
            return 6
        elif FeatureCategory =='Completed Hand Line':
            return 5
        elif FeatureCategory =='Completed Mixed Construction Line':
            return 4
        elif FeatureCategory =='Completed Fuel Break':
            return 3
        elif FeatureCategory =='Completed Burnout':
            return 2
        elif FeatureCategory =='Completed Plow Line':
            return 1
        elif FeatureCategory is None:
            return None
        else: 
            return 1000""",
        field_type="SHORT",
        enforce_domains="NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateField(
        in_table="Firelines_Diss",
        field="EngagementValue",
        expression="Reclass(!FirelineEngagement!)",
        expression_type="PYTHON3",
        code_block="""def Reclass(FirelineEngagement):
        if FirelineEngagement =='Held':
            return 3
        elif FirelineEngagement =='Not Engaged':
            return 2
        elif FirelineEngagement =='Not Held':
            return 1
        elif FirelineEngagement is None:
            return None
        else: 
            return 1000""",
    field_type="SHORT",
    enforce_domains="NO_ENFORCE_DOMAINS")
    # Buffer the dissolved firelines to create a 50-meter buffer around each line.
    arcpy.analysis.PairwiseBuffer("Firelines_Diss","Firelines_DissBuff", str(FirelineBuffer)+" Meters","NONE",None,"GEODESIC","0 DecimalDegrees")
    # Intersect the buffered firelines to identify overlaps between different fireline types.
    arcpy.analysis.PairwiseIntersect("Firelines_DissBuff","Line_DissBuffInt","ALL",None,"INPUT")
    arcpy.management.RepairGeometry("Line_DissBuffInt","DELETE_NULL","ESRI")
    # Dissolve the intersected buffered firelines again, this time including the newly calculated LineTypeValue.
    arcpy.analysis.PairwiseDissolve("Line_DissBuffInt","Line_DissBuffInt_diss","FeatureCategory;LineTypeValue;FirelineEngagement;EngagementValue",None,"MULTI_PART","")
    # Perform a union to combine all pieces of the buffered firelines, including overlaps and gaps.
    arcpy.analysis.Union("Line_DissBuffInt_diss #","Line_DissBuffIntUnion","ALL",None,"GAPS")
    # Count the overlapping features to determine the complexity of fireline intersections.
    arcpy.analysis.CountOverlappingFeatures("Line_DissBuffIntUnion","Line_DissBuffIntUn_CntOvp",1,"Line_CntOvp_Tbl")
    # Join the count and statistics back to the original features to include the overlap counts and stats.
    arcpy.management.JoinField("Line_CntOvp_Tbl","ORIG_OID","Line_DissBuffIntUnion","OBJECTID","LineTypeValue;FeatureCategory;FirelineEngagement;EngagementValue","NOT_USE_FM",None)
    arcpy.analysis.Statistics("Line_CntOvp_Tbl","Line_CntOvp_Stats_MxVlu","LineTypeValue MAX","OVERLAP_OID","")
    arcpy.analysis.Statistics("Line_CntOvp_Tbl","Line_CntOvp_Stats_Sum","LineTypeValue SUM","OVERLAP_OID","")
    arcpy.analysis.Statistics("Line_CntOvp_Tbl","Line_CntOvp_Stats_Concat","FeatureCategory CONCATENATE","OVERLAP_OID",", ")
    arcpy.analysis.Statistics("Line_CntOvp_Tbl","Line_CntOvp_Stats_ValueConcat","LineTypeValue CONCATENATE","OVERLAP_OID",", ")
    arcpy.analysis.Statistics("Line_CntOvp_Tbl","Line_CntOvp_EngVluMx","EngagementValue MAX","OVERLAP_OID","")
    arcpy.management.JoinField("Line_DissBuffIntUn_CntOvp","OBJECTID","Line_CntOvp_Stats_MxVlu","OVERLAP_OID","MAX_LineTypeValue","NOT_USE_FM",None)
    arcpy.management.JoinField("Line_DissBuffIntUn_CntOvp","OBJECTID","Line_CntOvp_Stats_Sum","OVERLAP_OID","SUM_LineTypeValue","NOT_USE_FM",None)
    arcpy.management.JoinField("Line_DissBuffIntUn_CntOvp","OBJECTID","Line_CntOvp_Stats_Concat","OVERLAP_OID","CONCATENATE_FeatureCategory","NOT_USE_FM",None)
    arcpy.management.JoinField("Line_DissBuffIntUn_CntOvp","OBJECTID","Line_CntOvp_Stats_ValueConcat","OVERLAP_OID","CONCATENATE_LineTypeValue","NOT_USE_FM",None)
    arcpy.management.JoinField("Line_DissBuffIntUn_CntOvp","OBJECTID","Line_CntOvp_EngVluMx","OVERLAP_OID","MAX_EngagementValue","NOT_USE_FM",None,"NO_INDEXES")
    # Erase the original buffer from the union of intersected buffers to define clear boundaries.
    arcpy.analysis.PairwiseErase("Firelines_DissBuff","Line_DissBuffIntUn_CntOvp","Firelines_DissBuff_erase",None)
    arcpy.management.RepairGeometry("Firelines_DissBuff_erase","DELETE_NULL","ESRI")
    # Convert any multipart features to single parts for both the erased buffer and the count overlap features.
    arcpy.management.MultipartToSinglepart("Line_DissBuffIntUn_CntOvp","Line_CntOvlp_snglpt")
    arcpy.management.MultipartToSinglepart("Firelines_DissBuff_erase","Line_DissBuffErase_snglpt")
    arcpy.management.DeleteField("Line_DissBuffErase_snglpt","BUFF_DIST; ORIG_FID","DELETE_FIELDS")
    arcpy.management.DeleteField("Line_CntOvlp_snglpt","COUNT_FC; ORIG_FID","DELETE_FIELDS")
    # Merge the single-part features back into a combined feature class.
    arcpy.management.Merge("Line_CntOvlp_snglpt;Line_DissBuffErase_snglpt","Line_Merge")
    # Add and calculate fields to store text representations of the line types and their codes.
    arcpy.management.AddField("Line_Merge","LineType","TEXT",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.AddField("Line_Merge","LineTypeCodes","TEXT",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.MakeFeatureLayer("Line_Merge","Line_Merge_Layer","LineTypeValue IS NULL")
    arcpy.management.CalculateField("Line_Merge_Layer","LineTypeCodes","!CONCATENATE_LineTypeValue!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateField("Line_Merge_Layer","LineType","!CONCATENATE_FeatureCategory!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.MakeFeatureLayer("Line_Merge","Line_Merge_Layer2","FeatureCategory IS NOT NULL")
    arcpy.management.CalculateField("Line_Merge_Layer2","LineType","!FeatureCategory!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateField("Line_Merge_Layer2","LineTypeCodes","!LineTypeValue!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.MakeFeatureLayer("Line_Merge","Line_Merge_Layer3","EngagementValue IS NULL")
    arcpy.management.CalculateField(
    in_table="Line_Merge_Layer3",
    field="FirelineEgagement",
    expression="Reclass(!MAX_EngagementValue!)",
    expression_type="PYTHON3",
    code_block="""def Reclass(MAX_EngagementValue):
    if MAX_EngagementValue == 3:
        return 'Held'
    elif MAX_EngagementValue == 2:
        return 'Not Engaged'
    elif MAX_EngagementValue == 1:
        return 'Not Held'
    elif MAX_EngagementValue is None:
        return 'error'
    else: 
        return 'error1'""",
    field_type="TEXT",
    enforce_domains="NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateField("Line_Merge_Layer3","EngagementValue","!MAX_EngagementValue!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.DeleteField("Line_Merge","CONCATENATE_FeatureCategory;CONCATENATE_LineTypeValue;FeatureCategory;LineTypeValue;MAX_EngagementValue","DELETE_FIELDS")
    # Prepare the final layers for output by calculating fields where necessary.
    arcpy.management.MakeFeatureLayer("Line_Merge","FnlLyr","MAX_LineTypeValue IS NULL")
    arcpy.management.CalculateField("FnlLyr","SUM_LineTypeValue","!LineTypeCodes!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateField("FnlLyr","MAX_LineTypeValue","!LineTypeCodes!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.MakeFeatureLayer("Line_Merge","FnlLyr2","COUNT_ IS NULL")
    arcpy.management.CalculateField("FnlLyr2","COUNT_","1","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.analysis.PairwiseDissolve("Line_Merge",IncidentName_BuffEnggmntLines_Datetime,"COUNT_;MAX_LineTypeValue;SUM_LineTypeValue;LineType;LineTypeCodes;FirelineEgagement",None,"MULTI_PART","")
    fc_Delete = ["Line_Merge","Line_CntOvp_EngVluMx","Line_DissBuffErase_snglpt","Line_CntOvlp_snglpt","Firelines_Diss","Firelines_DissBuff_erase","Line_DissBuffIntUn_CntOvp","Line_DissBuffIntUnion","Line_DissBuffInt_diss","Line_DissBuffInt","Firelines_DissBuff","Line_CntOvp_Tbl","Line_CntOvp_Stats_MxVlu","Line_CntOvp_Stats_Sum","Line_CntOvp_Stats_Concat","Line_CntOvp_Stats_ValueConcat"]
    for fc in fc_Delete:
        fc_path = os.path.join(localoutputws, fc)
        if arcpy.Exists(fc_path):
            arcpy.Delete_management(fc_path) 
except:
    arcpy.AddError("Error Overlapping Buffered Firelines... Exiting")
    print("Error")
    fc_Delete = ["Line_CntOvp_EngVluMx","Line_Merge","Perims","Line_DissBuffErase_snglpt","Line_CntOvlp_snglpt","Firelines_Diss","Firelines_DissBuff_erase","Line_DissBuffIntUn_CntOvp","Line_DissBuffIntUnion","Line_DissBuffInt_diss","Line_DissBuffInt","Firelines_DissBuff","Line_CntOvp_Tbl","Line_CntOvp_Stats_MxVlu","Line_CntOvp_Stats_Sum","Line_CntOvp_Stats_Concat","Line_CntOvp_Stats_ValueConcat"]
    for fc in fc_Delete:
        fc_path = os.path.join(localoutputws, fc)
        if arcpy.Exists(fc_path):
            arcpy.Delete_management(fc_path) 
    report_error()
    sys.exit()

print("Script Finished Running.")
arcpy.AddMessage("Script Finished Running.")
