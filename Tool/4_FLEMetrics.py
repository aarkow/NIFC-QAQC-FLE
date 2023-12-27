# -*- coding: utf-8 -*-
"""
Name: 
Author: Alex Arkowitz @ Colorado State University - alexander.arkowitz@colostate.edu
Date Created: 05/20/2023

Limitations:
Compatible with Python 3.x and ArcGIS Pro environments only which can be a limitation if the script is used in different versions of the software where the tools may have been updated or deprecated.
Assumes input datasets follow standard NIFC schemas.
The script is designed for National Interagency Fire Center specific fire-related datasets, limiting its applicability to other types of spatial analyses without significant modification
The processing power required also plays a role in the tool's performance and capabilities.

Usage:
This tool is a valuable asset for wildfire management professionals, offering a data-driven approach to enhance decision-making and strategic planning.
By automating the analysis of fireline engagement, it significantly boosts efficiency, reducing the time and potential for error compared to manual calculations.
The generated metrics allow for a transparent and replicable assessment of fire suppression tactics, aiding in the optimization of resource allocation and improving the efficacy of containment strategies.
It serves as an essential tool for post-incident analysis, helping to refine future firefighting efforts and resource deployment.
Furthermore, the tool's outputs can facilitate clearer communication with stakeholders and the public, providing a solid foundation for incident reporting and contributing
to collaborative efforts in wildfire management and community safety.

Description:
The Fire Line Engagement (FLE) Metrics Calculation script is to accompany a custom geoprocessing tool for ArcGIS Pro.

It automates the computation of several key metrics:
Holding Ratio (HTr): Held Line/Total Line. The proportion of the fireline that has held against the fire spread relative to the total fireline length.
Treatment Ratio (Tr): Total Line/Fire Perimeter. The overall fireline length in comparison to the fire perimeter, used to gauge the intensity of the fireline treatment.
Engagement Ratio (Er): (Held Line + Burned Over Line) / Total Line. The fraction of the fireline that is either held or burned over, providing insight into the engagement level of the fireline.
Held Engagement Ratio (HER): HeldLine/(HeldLine + BurnedOverLine). The portion of the held fireline compared to the total of held and burned-over firelines, indicating the success rate of holding lines.
Burned Treatment Ratio (BTR): BurnedOverLine/TotalLine. The ratio of the burned-over fireline to the total fireline, reflecting the areas where the fire overran containment efforts.
Not Engaged Treatment Ratio (NeTr): NotEngagedLine/TotalLine.The extent of firelines not engaged in active fire containment relative to the total fireline.
Held Area Proportion (HaPar): This metric is derived from the area of the buffered held line clipped to the held area divided by the total held area, aiding in calculating the total held line length depending on perimeter complexity.
Perimeter to Area Ratio (PrAr): A quick reference metric that relates the fire perimeter to the fire area, assisting in identifying the complexity of the fire's perimeter.

This tool operates under the assumption that firelines within 50 meters of each other should be consolidated into a single treatment line, thereby not tracking the intensity or type of fireline efforts within a geographic area. It also does not account for the number of passes over a given area.
The tool includes a flagging mechanism to highlight potential data anomalies or extremes in the metrics. If HTr, Er, HER, BTR, or NeTr fall outside the 0-1 range, the tool flags the output and triggers a warning message in ArcPro. Additionally, if Tr exceeds 3.25—a threshold established as the upper 95th percentile from a sample of 100 fires—the flag field will be populated, and a warning message will appear, prompting users to verify the data.
Users should note that the resolution, accuracy, and complexity of the input fire perimeter and fireline data can significantly influence the FLE metrics. The tool is designed to provide fire management professionals with an efficient and accurate means to assess fireline engagements, thereby supporting strategic decision-making and post-incident analysis.
"""
###-Import Libraries-###
import arcpy, os, sys, traceback
import pandas as pd
from sys import argv
from datetime import datetime, timezone
from arcpy import metadata as md

###-Functions-###

# Define a function to report any errors that occur during the execution of the script.
# This function gathers detailed information about the error and prints it for debugging.
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

# Initialize script variables, including input parameters and workspace paths.
try:
    # Grab & Format system date & time
    dt = datetime.now()
    datetime = dt.strftime("%Y%m%d_%H%M")
    # Set up directory paths based on the script's location.
    scrptfolder = os.path.dirname(__file__) #Returns the UNC of the folder where this python file sits
    folder_lst = os.path.split(scrptfolder) # Split the path into its components.
    local_root_fld = folder_lst[0] # Take the base directory for further path constructions.
    localoutputws = os.path.join(local_root_fld,"Output","Output.gdb")# Define the output workspace.
    scratchworkspace = os.path.join(local_root_fld,"ScratchWorkspace","scratch.gdb")# Define the scratch workspace.
    scratchfolder = os.path.join(local_root_fld,"ScratchWorkspace")
    FLEsourcemetadatapath = os.path.join(local_root_fld,"Metadata","FLE_Metrics.xml")# Metadata file path.
    # Retrieve input parameters from the ArcGIS tool interface.
    IncidentName = arcpy.GetParameterAsText(0)
    OpsData_QAQC_Firelines = arcpy.GetParameter(1)
    Perimeters = arcpy.GetParameter(2)
    FirelineEngagmentBuffer = arcpy.GetParameter(3)
    HeldLineBuffer = arcpy.GetParameter(4)
    #Format the buffer list parameter for mutiple ring buffer tool input
    FirelineEngagmentBuffList = [-FirelineEngagmentBuffer,FirelineEngagmentBuffer]

    # Define output feature class names based on the incident name and current datetime.
    OutputFLEMetricsName = "FLE_"+IncidentName+"_"+datetime
    Perims = "Perimeter_FLE_"+IncidentName+"_"+datetime

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
# Check if multiple perimeters have been provided. If so, the code will combine them into a single complex.
try:
    result = arcpy.GetCount_management(Perimeters)
    count = int(result.getOutput(0))
    # Get the count of perimeter features to determine if there are multiple perimeters.
    if count > 1:
        # If there is more than one perimeter, proceed to dissolve them into one complex.
        arcpy.AddMessage("Dissolving All Perimeters in the Complex and Taking Attribution From the Largest Perimeter")
        print("Dissolving All Perimeters in the Complex and Taking Attribution From the Largest Perimeter")
        arcpy.management.CopyFeatures(Perimeters,"PerimsToDiss")
        lstFields = arcpy.ListFields("PerimstoDiss")
        lstfieldNames = [f.name for f in lstFields]
        # Check for the 'attr_FireMgmtComplexity' field, which may hold important management information.
        # If the complexity field exists, assess if there's more than one team's complexity to concatenate.
        if "attr_FireMgmtComplexity" in lstfieldNames:
            #Team Cmplx Coding. If only one perim in the complex has a FireMgmtCmplx Team, it will be attributed to all. If several do, they will be concatenated.
            arcpy.management.MakeFeatureLayer("PerimsToDiss","Perims_Teams","attr_FireMgmtComplexity IS NOT NULL")
            resultteams = arcpy.GetCount_management("Perims_Teams")
            count2 = int(resultteams.getOutput(0))
            # Depending on the number of complexities, concatenate the values.
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
        # If the 'attr_FireMgmtComplexity' field does not exist, add it.
        if "attr_FireMgmtComplexity" not in lstfieldNames:
            arcpy.management.AddField("PerimsToDiss","attr_FireMgmtComplexity","TEXT",None,None,None,"","NULLABLE","NON_REQUIRED","")
            arcpy.management.CalculateField("PerimsToDiss","attr_FireMgmtComplexity",'"None"',"PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
        #Make sure geodesic acreage was calculated correctly.
        lstFields = arcpy.ListFields("PerimstoDiss")
        lstfieldNames = [f.name for f in lstFields]
        if "GoedesicAcreage" in lstfieldNames:
            arcpy.management.DeleteField("PerimsToDiss","GeodesicAcreage","DELETE_FIELDS")
        arcpy.management.AddField("PerimstoDiss","GeodesicAcreage","DOUBLE",None,None,None,"","NULLABLE","NON_REQUIRED","")
        arcpy.management.CalculateGeometryAttributes("PerimstoDiss","GeodesicAcreage AREA_GEODESIC","","ACRES",None,"SAME_AS_INPUT")
        arcpy.management.MakeFeatureLayer("PerimsToDiss","Perimeters_Lrgst","GeodesicAcreage = (SELECT MAX(GeodesicAcreage) FROM PerimsToDiss)")
        # After all dissolving and attribution is done, export the complex perimeter as a new feature class.
        arcpy.conversion.ExportFeatures("Perimeters_Lrgst","Perimeters_LrgstPerim")
        arcpy.management.CalculateField("Perimeters_LrgstPerim","Joinfield","1")
        arcpy.management.CalculateField("PerimsToDiss","Joinfield","1")
        arcpy.management.DeleteField("PerimsToDiss","attr_IrwinID;attr_IncidentName","DELETE_FIELDS")
        arcpy.management.JoinField("PerimsToDiss","Joinfield","Perimeters_LrgstPerim","Joinfield","attr_IncidentName;attr_IrwinID")
        arcpy.analysis.PairwiseDissolve("PerimsToDiss",Perims,"attr_IncidentName;attr_IrwinID;attr_FireMgmtComplexity",None,"MULTI_PART")
        arcpy.management.CalculateField(Perims,"attr_IncidentName",'!attr_IncidentName!+ " Complex"',"PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    # If only one perimeter is provided, simply copy it to the new feature class.
    elif count == 1:
        lstFields = arcpy.ListFields(Perimeters)
        lstfieldNames = [f.name for f in lstFields]
        if "attr_FireMgmtComplexity" in lstfieldNames:
            print("Fire Mgmt Cmplx Field Present")
        else:
            arcpy.management.AddField(Perimeters,"attr_FireMgmtComplexity","TEXT",None,None,None,"","NULLABLE","NON_REQUIRED","")
        lstFields = arcpy.ListFields(Perimeters)
        lstfieldNames = [f.name for f in lstFields]
        if "GoedesicAcreage" in lstfieldNames:
            arcpy.management.DeleteField(Perimeters,"GeodesicAcreage","DELETE_FIELDS")
        arcpy.management.AddField(Perimeters,"GeodesicAcreage","DOUBLE",None,None,None,"","NULLABLE","NON_REQUIRED","")
        arcpy.management.CalculateGeometryAttributes(Perimeters,"GeodesicAcreage AREA_GEODESIC","","ACRES",None,"SAME_AS_INPUT")
        arcpy.management.CopyFeatures(Perimeters,Perims)
    elif count == 0:
        arcpy.AddError("No Features Provided in Perimeter Feature Class... Exiting")
        print("No Features Provided in Perimeter Feature Class... Exiting")

    fc_Delete = ["Perimeters_Lrgst","FLE_Output_Dateti_Statistics","Perimeters_LrgstPerim","PerimsToDiss"]
    for fc in fc_Delete:
        fc_path = os.path.join(localoutputws, fc)
        if arcpy.Exists(fc_path):
            arcpy.Delete_management(fc_path)
except:
    arcpy.AddError("Error Dissolving Perimeters in the Complex... Exiting")
    print("Error Dissolving Perimeters in the Complex... Exiting")
    fc_Delete = ["Perimeters_Lrgst","FLE_Output_Dateti_Statistics","Perimeters_LrgstPerim","PerimsToDiss"]
    for fc in fc_Delete:
        fc_path = os.path.join(localoutputws, fc)
        if arcpy.Exists(fc_path):
            arcpy.Delete_management(fc_path) 
    report_error()
    sys.exit()


'''
This section of code buffers firelines to aggregate those within close proximity into unified polygons, distinguishing between different types of fireline engagement such as 'held', 'burned over', and 'not engaged'.
Next, the script calculates areas and lengths for these different engagement types and uses these figures to compute several key metrics.
These metrics, such as the 'HaPar' ratio (Buffered Held Line Clipped to Held Area/Total Held Area) and the fire perimeter to fire area ratio ('PrAr'), provide
insights into the performance of fire management efforts. For instance, they indicate the proportion of firelines holding up against the fire and the complexity of the fire's perimeter.
Additionally, the script is designed to flag any unusual or extreme values in these metrics that may indicate potential data errors or extraordinary situations that require attention.
This flagging mechanism is crucial for quality control, ensuring that the metrics provided are within reasonable and expected ranges.
Upon completion, the tool exports the results to both a feature class and an Excel spreadsheet. This dual output offers a means to visually
interpret the data via GIS software and to perform further statistical analysis or record-keeping in a tabular format.
'''
try:
    arcpy.AddMessage("Grouping Firelines Based on Proximity")
    print("Grouping Firelines Based on Proximity")
    #Buffer firelines to group lines into one polygon within 50m of eachother 
    arcpy.analysis.PairwiseBuffer(OpsData_QAQC_Firelines,"Lines_Buff25","25 Meters","ALL",None,"GEODESIC","0 DecimalDegrees")
    arcpy.analysis.PairwiseBuffer("Lines_Buff25","Lines_Buff5","-20 Meters","ALL",None,"GEODESIC","0 DecimalDegrees")
    #Create rings from fire perimeter to ID held, not engaged, and burned over areas
    arcpy.analysis.MultipleRingBuffer(Perims,"PerimMltRngBuff",FirelineEngagmentBuffList,"Meters","Buff","ALL","FULL","GEODESIC")
    #Create subset of held area
    arcpy.management.MakeFeatureLayer("PerimMltRngBuff","PerimMltRngBuff_Held","Buff = "+(str(FirelineEngagmentBuffer)),None)
    #Create subset of burned over area
    arcpy.management.MakeFeatureLayer("PerimMltRngBuff","PerimMltRngBuff_BurnedOver","Buff = -"+(str(FirelineEngagmentBuffer)),None)
    #Clip lines along held area
    arcpy.analysis.PairwiseClip("Lines_Buff5","PerimMltRngBuff_Held","HeldLine",None)
    #Clip lines along burned over area
    arcpy.analysis.PairwiseClip("Lines_Buff5","PerimMltRngBuff_BurnedOver","BurnedOverLine",None)
    #Erase held and burned over area from "lines" to create subset of not engaged
    arcpy.analysis.PairwiseErase("Lines_Buff5","PerimMltRngBuff","NotEngaged",None)
    #Check if fire doesnt have held, not engaged, or burned over line
    #Held
    HeldResult = arcpy.management.GetCount("HeldLine")
    if str(HeldResult) == "0":
        arcpy.AddMessage("No Held Line")
        print("No Held Line")
    #Burned Over
    BurnedOverResult = arcpy.management.GetCount("BurnedOverLine")
    if str(BurnedOverResult) == "0":
        arcpy.AddMessage("No Burned Over Line")
        print("No Burned Over Line")
    #Not Engaged
    NotEngagedResult = arcpy.management.GetCount("NotEngaged")
    if str(NotEngagedResult) == "0":
        arcpy.AddMessage("No Not Engaged Line")
        print("No Not Engaged Line")
    if str(HeldResult) == "0" and str(BurnedOverResult) == "0" and str(NotEngagedResult) == "0":
        arcpy.AddError("Zero lines found. Exiting")
        print("Zero lines found. Exiting...")
        fc_Delete = ["BurnedOverLine","FLE_Output_Dateti_Statistics","FLE_Output_Sums","HeldFirePerimBuffer","HeldLine","HeldLine_100mBuff","HeldLine_Clip_HeldBuff","Lines_Buff5","Lines_Buff25","NotEngaged","PerimMltRngBuff","FLE_Output_HeldOverwrite"]
        for fc in fc_Delete:
            fc_path = os.path.join(localoutputws, fc)
            if arcpy.Exists(fc_path):
                arcpy.Delete_management(fc_path)
        sys.exit()

    if str(HeldResult) != "0":
        #Buffer the held line polygons to X meters for clipping to the held perimeter. 5m is taken off because they have already been turned into a 5m buffer.
        arcpy.analysis.PairwiseBuffer("HeldLine","HeldLine_100mBuff", (str(int(HeldLineBuffer-5)))+" Meters","ALL",None,"GEODESIC","0 DecimalDegrees")
        #Clip the buffered held area to the perimeter held area
        arcpy.analysis.PairwiseClip("HeldLine_100mBuff","PerimMltRngBuff_Held","HeldLine_Clip_HeldBuff",None)
        #Create FC from layer to calculate stats such as area
        arcpy.conversion.ExportFeatures("PerimMltRngBuff_Held","HeldFirePerimBuffer")
        #Add and calculate fields to hold area and field to link fields to share attributes later
        arcpy.management.AddField("HeldLine_Clip_HeldBuff","HeldAreaSqMt","DOUBLE")
        arcpy.management.AddField("HeldFirePerimBuffer","HeldPerimAreaSqMt","DOUBLE")
        arcpy.management.AddField("HeldLine_Clip_HeldBuff","LinkingField","SHORT")
        arcpy.management.AddField("HeldFirePerimBuffer","LinkingField","SHORT")

        #Calculate Area and create a field to link the 2 feature classes together
        arcpy.management.CalculateGeometryAttributes("HeldLine_Clip_HeldBuff","HeldAreaSqMt AREA_GEODESIC","","SQUARE_METERS",None,"SAME_AS_INPUT")
        arcpy.management.CalculateGeometryAttributes("HeldFirePerimBuffer","HeldPerimAreaSqMt AREA_GEODESIC","","SQUARE_METERS",None,"SAME_AS_INPUT")
        arcpy.management.CalculateField("HeldLine_Clip_HeldBuff","LinkingField","1","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
        arcpy.management.CalculateField("HeldFirePerimBuffer","LinkingField","1","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
        #Send the the held perimeter buffer area to the held buffer feature class
        arcpy.management.JoinField("HeldLine_Clip_HeldBuff","LinkingField","HeldFirePerimBuffer","LinkingField","HeldPerimAreaSqMt","NOT_USE_FM",None)
        #Create and calculate the HaPar ratio which is area held vs total held area
        arcpy.management.AddField("HeldLine_Clip_HeldBuff","HaPar","DOUBLE",None,None,None,"","NULLABLE","NON_REQUIRED","")
        arcpy.management.CalculateField("HeldLine_Clip_HeldBuff","HaPar","!HeldAreaSqMt!/!HeldPerimAreaSqMt!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
        #Join the HaPar to the Held Line feature class
        arcpy.management.AddField("HeldLine","LinkingField","SHORT",None,None,None,"","NULLABLE","NON_REQUIRED","")
        arcpy.management.CalculateField("HeldLine","LinkingField","1","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
        arcpy.management.JoinField("HeldLine","LinkingField","HeldLine_Clip_HeldBuff","LinkingField","HaPar","NOT_USE_FM",None)

    #If held clip area doesnt have any lines, insert zeros.
    if str(HeldResult) == "0":

        arcpy.management.AddField("HeldLine","HaPar","DOUBLE",None,None,None,"","NULLABLE","NON_REQUIRED","")
        arcpy.management.CalculateField("HeldLine","HaPar","0","PYTHON3","","DOUBLE","NO_ENFORCE_DOMAINS")
        #Join the HaPar to the Held Line feature class
        arcpy.management.AddField("HeldLine","LinkingField","SHORT",None,None,None,"","NULLABLE","NON_REQUIRED","")
        arcpy.management.CalculateField("HeldLine","LinkingField","1","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
        
        Heldfields = ['Shape_Length','Shape_Area','HaPar','LinkingField']
        with arcpy.da.InsertCursor("HeldLine", Heldfields) as cursor:
            # Create new row. Set default values on distance and CFCC code
            for x in range(0, 1):
                cursor.insertRow((0, 0, 0, 1))

    #Uncomment these next 2 lines out if you want a fc showing the held area and the held line buffer
    #arcpy.conversion.ExportFeatures("HeldLine_Clip_HeldBuff","HeldLineBuffer_"+IncidentName)
    #arcpy.conversion.ExportFeatures("PerimMltRngBuff_Held","HeldFirePerimBuffer_"+IncidentName)

    #Calculate the fire perimeter and link it to the held line feature to calculate HaPar
    #First check if perimeter has fireperimetermtrs field already and delete if it does.
    lstFields = arcpy.ListFields(Perims)
    lstfieldNames = [f.name for f in lstFields]
    if "FirePerimeterMtrs" in lstfieldNames:
        arcpy.management.DeleteField(Perims,"FirePerimeterMtrs","DELETE_FIELDS")
    if "GeodesAreaMt" in lstfieldNames:
        arcpy.management.DeleteField(Perims,"GeodesAreaMt","DELETE_FIELDS")
    arcpy.management.AddField(Perims,"FirePerimeterMtrs","DOUBLE",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.AddField(Perims,"LinkingField","SHORT",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.CalculateField(Perims,"LinkingField","1","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateGeometryAttributes(Perims,"FirePerimeterMtrs PERIMETER_LENGTH_GEODESIC","METERS","",None,"SAME_AS_INPUT")
    arcpy.management.AddField(Perims,"IncGeodesAreaSqMt","DOUBLE",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.CalculateGeometryAttributes(Perims,"IncGeodesAreaSqMt AREA_GEODESIC","METERS","SQUARE_METERS",None,"SAME_AS_INPUT")
    arcpy.management.JoinField("HeldLine","LinkingField",Perims,"LinkingField",["FirePerimeterMtrs", "IncGeodesAreaSqMt","attr_FireMgmtComplexity"],"NOT_USE_FM",None)
    #Calculate the held line by multiplying the fire perimeter by the HaPar ratio
    arcpy.management.AddField("HeldLine","HeldLine","DOUBLE",None,None,None)
    arcpy.management.CalculateField("HeldLine","HeldLine","!FirePerimeterMtrs!*!HaPar!","PYTHON3","","DOUBLE","NO_ENFORCE_DOMAINS")
    #Add fields to hold engagement status
    arcpy.management.AddField("HeldLine","Engagement","TEXT",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.AddField("BurnedOverLine","Engagement","TEXT",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.AddField("NotEngaged","Engagement","TEXT",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.CalculateField("HeldLine","Engagement",'"Held"',"PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateField("NotEngaged","Engagement",'"Not Engaged"',"PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateField("BurnedOverLine","Engagement",'"Burned Over"',"PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    #Create and calculate fire line perimeters and line lengths
    arcpy.management.AddField("NotEngaged","NotEngagedPerimeterSqMt","DOUBLE",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.AddField("NotEngaged","NotEngagedLineLengthSqMt","DOUBLE",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.AddField("BurnedOverLine","BurnedOverPerimeterSqMt","DOUBLE",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.AddField("BurnedOverLine","BurnedOverLineLengthSqMt","DOUBLE",None,None,None,"","NULLABLE","NON_REQUIRED","")

    #Burned Over
    if str(BurnedOverResult) == "0":
        BOfields = ['Engagement', 'BurnedOverPerimeterSqMt','BurnedOverLineLengthSqMt']
        with arcpy.da.InsertCursor("BurnedOverLine", BOfields) as cursor:
            # Create new row. Set default values on distance and CFCC code
            for x in range(0, 1):
                cursor.insertRow(('Burned Over', 0, 0 ))
    if str(BurnedOverResult) != "0":
        arcpy.management.CalculateGeometryAttributes("BurnedOverLine","BurnedOverPerimeterSqMt PERIMETER_LENGTH_GEODESIC","METERS","",None,"SAME_AS_INPUT")
        arcpy.management.CalculateField("BurnedOverLine","BurnedOverLineLengthSqMt","!BurnedOverPerimeterSqMt!/2","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
        
    #Not Engaged
    if str(NotEngagedResult) == "0":
        NEfields = ['Engagement', 'NotEngagedPerimeterSqMt','NotEngagedLineLengthSqMt']
        with arcpy.da.InsertCursor("NotEngaged", NEfields) as cursor:
            # Create new row. Set default values on distance and CFCC code
            for x in range(0, 1):
                cursor.insertRow(('Not Engaged', 0, 0 ))
    if str(NotEngagedResult) != "0":
        arcpy.management.CalculateGeometryAttributes("NotEngaged","NotEngagedPerimeterSqMt PERIMETER_LENGTH_GEODESIC","METERS","",None,"SAME_AS_INPUT")
        arcpy.management.CalculateField("NotEngaged","NotEngagedLineLengthSqMt","!NotEngagedPerimeterSqMt!/2","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
        
    #Merge the different engagement types together
    arcpy.management.Merge("HeldLine;BurnedOverLine;NotEngaged",OutputFLEMetricsName)
    #Add fields to hold final line lengths
    arcpy.management.AddField(OutputFLEMetricsName,"BurnedOverLine","DOUBLE",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.AddField(OutputFLEMetricsName,"NotEngagedLine","DOUBLE",None,None,None,"","NULLABLE","NON_REQUIRED","")
    
    #Populate all fields for all engagement types to hold the values for Held, Burned Over, and Not Engaged in order to make metrics easier to calculate
    arcpy.management.CalculateField(OutputFLEMetricsName,"BurnedOverLine","!BurnedOverLineLengthSqMt!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateField(OutputFLEMetricsName,"NotEngagedLine","!NotEngagedLineLengthSqMt!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")   
    arcpy.analysis.Statistics(OutputFLEMetricsName,"FLE_Output_Sums","FirePerimeterMtrs SUM;IncGeodesAreaSqMt SUM;HeldLine SUM;BurnedOverLine SUM;NotEngagedLine SUM",None,"")
    arcpy.management.AddField("FLE_Output_Sums","LinkingField","SHORT",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.CalculateField("FLE_Output_Sums","LinkingField","1","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.JoinField(OutputFLEMetricsName,"LinkingField","FLE_Output_Sums","LinkingField","SUM_NotEngagedLine;SUM_IncGeodesAreaSqMt;SUM_HeldLine;SUM_FirePerimeterMtrs;SUM_BurnedOverLine")
    arcpy.management.CalculateField(OutputFLEMetricsName,"NotEngagedLine","!SUM_NotEngagedLine!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateField(OutputFLEMetricsName,"BurnedOverLine","!SUM_BurnedOverLine!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateField(OutputFLEMetricsName,"FirePerimeterMtrs","!SUM_FirePerimeterMtrs!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateField(OutputFLEMetricsName,"HeldLine","!SUM_HeldLine!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateField(OutputFLEMetricsName,"IncGeodesAreaSqMt","!SUM_IncGeodesAreaSqMt!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    #Bring in Inc name as FCName and IRWINID to FLE output
    arcpy.management.AddField(OutputFLEMetricsName,"FCName","TEXT",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.AddField(OpsData_QAQC_Firelines,"LinkingField","SHORT",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.CalculateField(OpsData_QAQC_Firelines,"LinkingField","1","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.JoinField(OutputFLEMetricsName,"LinkingField",OpsData_QAQC_Firelines,"LinkingField","IncidentName;IRWINID")
    arcpy.management.CalculateField(OutputFLEMetricsName,"FCName","!IncidentName!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.DeleteField(OpsData_QAQC_Firelines,"LinkingField","DELETE_FIELDS")
    arcpy.management.DeleteField(OutputFLEMetricsName,"IncidentName;LinePerimeter;LineLength;BurnedOverPerimeterSqMt;BurnedOverLineLengthSqMt;NotEngagedPerimeterSqMt;NotEngagedLineLengthSqMt;SUM_IncGeodesAreaSqMt;SUM_NotEngagedLine;SUM_HeldLine;SUM_FirePerimeterMtrs;SUM_BurnedOverLine;LinkingField","DELETE_FIELDS")
    
    #Add Fields and calculate metrics
    arcpy.management.AddField(OutputFLEMetricsName,"HTr","DOUBLE",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.AddField(OutputFLEMetricsName,"TR","DOUBLE",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.AddField(OutputFLEMetricsName,"ER","DOUBLE",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.AddField(OutputFLEMetricsName,"HER","DOUBLE",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.AddField(OutputFLEMetricsName,"BTR","DOUBLE",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.AddField(OutputFLEMetricsName,"NETR","DOUBLE",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.AddField(OutputFLEMetricsName,"PrAr","DOUBLE",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.AddField(OutputFLEMetricsName,"TotalLine","DOUBLE",None,None,None,"","NULLABLE","NON_REQUIRED","")
    arcpy.management.CalculateField(OutputFLEMetricsName,"TotalLine","!HeldLine! + !BurnedOverLine! + !NotEngagedLine!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateField(OutputFLEMetricsName,"HTr","!HeldLine! / !TotalLine!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateField(OutputFLEMetricsName,"Tr","!TotalLine!/!FirePerimeterMtrs!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateField(OutputFLEMetricsName,"Er","(!HeldLine! + !BurnedOverLine!)/!TotalLine!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateField(OutputFLEMetricsName,"HER","!HeldLine!/(!HeldLine! + !BurnedOverLine!)","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    fields = ['HER']
    cursor = arcpy.da.SearchCursor(OutputFLEMetricsName, fields)
    # Loop through the cursor and assign the first value to each variable
    for row in cursor:
        HERvalue = (row[0])
        if HERvalue is None:
            arcpy.management.CalculateField(OutputFLEMetricsName,"HER","0","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
        # Break after processing the first row
        break
    # Close the cursor
    del cursor
    arcpy.management.CalculateField(OutputFLEMetricsName,"BTR","!BurnedOverLine!/!TotalLine!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateField(OutputFLEMetricsName,"NeTr","!NotEngagedLine!/!TotalLine!","PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")
    arcpy.management.CalculateField(OutputFLEMetricsName,"PrAr","!FirePerimeterMtrs!/!IncGeodesAreaSqMt!","PYTHON3","","DOUBLE","NO_ENFORCE_DOMAINS")

    #delete processing data
    fc_Delete = ["HeldFirePerimBuffer","BurnedOverLine","OutputFLEMetrics_ExportTable","FLE_Output_Dateti_Statistics","FLE_Output_Sums","HeldLine","HeldLine_100mBuff","HeldLine_Clip_HeldBuff","Lines_Buff5","Lines_Buff25","NotEngaged","PerimMltRngBuff","FLE_Output_HeldOverwrite"]
    for fc in fc_Delete:
        fc_path = os.path.join(localoutputws, fc)
        if arcpy.Exists(fc_path):
            arcpy.Delete_management(fc_path)
    
    #Add a flag field to ID if metrics fall outside of possible bounds. A better way to code this exists and should be explored/written in.
    arcpy.management.AddField(OutputFLEMetricsName,"FLE_Flag","TEXT")
    arcpy.management.CalculateField(OutputFLEMetricsName,"FLE_Flag",'"None"',"PYTHON3","","TEXT","NO_ENFORCE_DOMAINS")

    fields = ['HTr','TR','ER','HER','BTR','NETR']
    cursor = arcpy.da.SearchCursor(OutputFLEMetricsName, fields)
    # Loop through the cursor and assign the first value to each variable
    for row in cursor:
        HTRvalue = float(row[0])
        TRvalue = float(row[1])
        ERvalue = float(row[2])
        HERvalue = float(row[3])
        BTRvalue = float(row[4])
        NETRvalue = float(row[5])
        # Break after processing the first row
        break
    # Close the cursor
    del cursor

    if HTRvalue >1 or ERvalue >1 or HERvalue >1 or BTRvalue >1 or NETRvalue >1 or HTRvalue <0 or ERvalue <0 or HERvalue <0 or BTRvalue <0 or NETRvalue <0:
        arcpy.management.CalculateField(OutputFLEMetricsName,"FLE_Flag",expression='"HTR ER HER BTR or NETR fall outside of possible range"',expression_type="PYTHON3", code_block="",field_type="TEXT",enforce_domains="NO_ENFORCE_DOMAINS")
        arcpy.AddWarning("One or more FLE metrics invalid")

    FlagField = ['FLE_Flag']
    FlagFieldValue = [row[0] for row in arcpy.da.SearchCursor(OutputFLEMetricsName, FlagField)]

    if str(FlagFieldValue) == "HTR ER HER BTR or NETR fall outside of possible range" and TRvalue > 3.25:
        arcpy.management.CalculateField(OutputFLEMetricsName,"FLE_Flag",'"Check data as TR value is extreme. Also, HTR ER HER BTR or NETR fall outside of possible range. "',"PYTHON3", "","TEXT","NO_ENFORCE_DOMAINS")
        arcpy.AddWarning("One or more FLE metrics invalid")
        
    if str(FlagFieldValue) == 'None' and TRvalue > 3.25:
        arcpy.management.CalculateField(OutputFLEMetricsName,"FLE_Flag",'"Check data as TR value is in top 95 percentile."',"PYTHON3", "","TEXT","NO_ENFORCE_DOMAINS")
        arcpy.AddWarning("TR Value is considered extreme. Check data.")

    #Export FC and overwrite old one to sort fields in an appealing way")
    arcpy.conversion.ExportFeatures(OutputFLEMetricsName,"SortedExportFeature","","NOT_USE_ALIAS",'FCName "FCName" true true false 255 Text 0 0,First,#,'+OutputFLEMetricsName+',FCName,0,254;IRWINID "IRWINID" true true false 50 Text 0 0,First,#,'+OutputFLEMetricsName+',IRWINID,0,49;Engagement "Engagement" true true false 255 Text 0 0,First,#,'+OutputFLEMetricsName+',Engagement,0,254;FirePerimeterMtrs "FirePerimeterMtrs" true true false 8 Double 0 0,First,#,'+OutputFLEMetricsName+',FirePerimeterMtrs,-1,-1;IncGeodesAreaSqMt "IncGeodesAreaSqMt" true true false 8 Double 0 0,First,#,'+OutputFLEMetricsName+',IncGeodesAreaSqMt,-1,-1;TotalLine "TotalLine" true true false 8 Double 0 0,First,#,'+OutputFLEMetricsName+',TotalLine,-1,-1;HeldLine "HeldLine" true true false 8 Double 0 0,First,#,'+OutputFLEMetricsName+',HeldLine,-1,-1;BurnedOverLine "BurnedOverLine" true true false 8 Double 0 0,First,#,'+OutputFLEMetricsName+',BurnedOverLine,-1,-1;NotEngagedLine "NotEngagedLine" true true false 8 Double 0 0,First,#,'+OutputFLEMetricsName+',NotEngagedLine,-1,-1;HTr "HTr" true true false 8 Double 0 0,First,#,'+OutputFLEMetricsName+',HTr,-1,-1;TR "TR" true true false 8 Double 0 0,First,#,'+OutputFLEMetricsName+',TR,-1,-1;ER "ER" true true false 8 Double 0 0,First,#,'+OutputFLEMetricsName+',ER,-1,-1;HER "HER" true true false 8 Double 0 0,First,#,'+OutputFLEMetricsName+',HER,-1,-1;BTR "BTR" true true false 8 Double 0 0,First,#,'+OutputFLEMetricsName+',BTR,-1,-1;NETR "NETR" true true false 8 Double 0 0,First,#,'+OutputFLEMetricsName+',NETR,-1,-1;HaPar "HaPar" true true false 8 Double 0 0,First,#,'+OutputFLEMetricsName+',HaPar,-1,-1;PrAr "PrAr" true true false 8 Double 0 0,First,#,'+OutputFLEMetricsName+',PrAr,-1,-1;attr_FireMgmtComplexity "attr_FireMgmtComplexity" true true false 25 Text 0 0,First,#,'+OutputFLEMetricsName+',attr_FireMgmtComplexity,0,24;FLE_Flag "FLE_Flag" true true false 255 Text 0 0,First,#,'+OutputFLEMetricsName+',FLE_Flag,0,254;Shape_Length "Shape_Length" false true true 8 Double 0 0,First,#,'+OutputFLEMetricsName+',Shape_Length,-1,-1;Shape_Area "Shape_Area" false true true 8 Double 0 0,First,#,'+OutputFLEMetricsName+',Shape_Area,-1,-1',None)
    arcpy.conversion.ExportFeatures("SortedExportFeature",OutputFLEMetricsName)

    #Fill all atributes for FCName and IRWIN, not just the top one.
    field_to_update = 'FCName'
    # Find the first non-null value in the field
    with arcpy.da.SearchCursor(OutputFLEMetricsName, [field_to_update]) as cursor:
        for row in cursor:
            if row[0] is not None:
                first_non_null_value = row[0]
                break
    # Update nulls in the field with the first non-null value
    with arcpy.da.UpdateCursor(OutputFLEMetricsName, [field_to_update]) as cursor:
        for row in cursor:
            if row[0] is None:
                row[0] = first_non_null_value
                cursor.updateRow(row)
    field_to_update = 'IRWINID'     
    with arcpy.da.SearchCursor(OutputFLEMetricsName, [field_to_update]) as cursor:
        for row in cursor:
            if row[0] is not None:
                first_non_null_value = row[0]
                break
    # Update nulls in the field with the first non-null value
    with arcpy.da.UpdateCursor(OutputFLEMetricsName, [field_to_update]) as cursor:
        for row in cursor:
            if row[0] is None:
                row[0] = first_non_null_value
                cursor.updateRow(row)
    
    #Export a table of the metrics
    arcpy.conversion.ExportTable(OutputFLEMetricsName,"OutputFLEMetrics_ExportTable","HaPar IS NOT NULL",)
    arcpy.management.DeleteField("OutputFLEMetrics_ExportTable","Shape_Length;Shape_Area;Engagement","DELETE_FIELDS")
    arcpy.conversion.TableToExcel("OutputFLEMetrics_ExportTable",(os.path.join(local_root_fld,"Output","Excel_FLE_Output","FLE_Metrics_"+IncidentName+"_"+datetime+".xlsx")),"NAME","CODE")

    #delete processing data
    fc_Delete = ["SortedExportFeature","OutputFLEMetrics_ExportTable"]
    for fc in fc_Delete:
        fc_path = os.path.join(localoutputws, fc)
        if arcpy.Exists(fc_path):
            arcpy.Delete_management(fc_path)

    #This section adds the name of the excel file as a column in the excel file iteself for better tracking when building the master FLE spreadsheet
    excel_file_path = os.path.join(local_root_fld,"Output","Excel_FLE_Output","FLE_Metrics_"+IncidentName+"_"+datetime+".xlsx")

    df = pd.read_excel(excel_file_path)
    # Create the new column 'IncName' and populate it
    df['IncName'] = IncidentName + "_" + datetime

    # Save the updated dataframe back to the Excel file
    df.to_excel(excel_file_path, index=False)

except:
    arcpy.AddError("Error... Exiting")
    print("Error... Exiting")
    fc_Delete = ["BurnedOverLine","SortedExportFeature","OutputFLEMetrics_ExportTable","FLE_Output_Dateti_Statistics","FLE_Output_Sums","HeldFirePerimBuffer","HeldLine","HeldLine_100mBuff","HeldLine_Clip_HeldBuff","Lines_Buff5","Lines_Buff25","NotEngaged","PerimMltRngBuff","FLE_Output_HeldOverwrite"]
    for fc in fc_Delete:
        fc_path = os.path.join(localoutputws, fc)
        if arcpy.Exists(fc_path):
            arcpy.Delete_management(fc_path)
    report_error()
    sys.exit()

try:
    print("Writing Metadata to Output Feature Classes")
    arcpy.AddMessage("Writing Metadata to Output Feature Classes")
    tgt_item_md = md.Metadata(OutputFLEMetricsName)
    tgt_item_md.importMetadata(FLEsourcemetadatapath)
    tgt_item_md.save()
except:
    arcpy.AddWarning("Possible Error Importing Metadata.")
    print("Error Importing Metadata.")
    report_error()

#This section will append the new FLE metrics to a master FLE file for easier data analysis and tracking.
try:
    source_file = os.path.join(local_root_fld,"Output","Excel_FLE_Output","FLE_Metrics_"+IncidentName+"_"+datetime+".xlsx")
    master_file = os.path.join(local_root_fld,"Output","Excel_FLE_Output","FLE_Master.xlsx")

    # Load the source file into a DataFrame with the first row as the header
    source_df = pd.read_excel(source_file)

    if not os.path.exists(master_file):
        source_df.to_excel(master_file, index=False)
    else:
        # Load the master file into a DataFrame
        master_df = pd.read_excel(master_file)

        # Append the values from the source file to the master file
        master_df = pd.concat([master_df, source_df], ignore_index=True, axis=0)

        # Save the updated master DataFrame back to the master file
        master_df.to_excel(master_file, index=False)


    arcpy.AddMessage("Appended new FLE XLS records to the FLE Master XLS.")
    print("Appended new FLE XLS records to the FLE Master XLS.")
    
except:
    arcpy.AddWarning("Error Appending new FLE XLS records to the FLE Master XLS. Make sure a master xls is available by copying a singular FLE output and name it 'FLE_Master.xlsx'")
    print("Error Appending new FLE XLS records to the FLE Master XLS.")
    report_error()

print("Script Finished Running.")
arcpy.AddMessage("Script Finished Running.")
