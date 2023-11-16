# NIFC-QAQC-FLE
## Overview:
#### This repository contains a suite of tools designed for wildfire data researchers and fire management professionals.  These tools facilitate the creation of fireline engagement metrics, aiding in the evaluation and improvement of wildfire management strategies. These scripts and its accompanying directory should be downloaded onto a local drive. The user can then open an ArcGIS Pro 3.X project and direct the ArcCatalog to the files. The ArcToolbox that uses the scripts can be found in the Tool folder.


### Background:
The increasing availability of spatially explicit fireline records enables the evaluation of containment strategies using fireline effectiveness (FLE) metrics. These metrics are based on measures like the length of the final wildfire perimeter and the performance of firelines (burned over, held, or not engaged). This toolkit aims to expand the application of FLE metrics beyond case studies, enhancing the understanding and evaluation of incident-level strategy effectiveness.


### General Workflow:
Data Preparation: Start by using Tool 1 to ensure the integrity and accuracy of fire perimeter data. Check the output attribution to ensure that your perimeter(s) of interest do not have duplicates with different IRWIN identification numbers or incident names. If so, use other data sources to verify the correct perimeter. Export your fire perimeter as a single feature class, and use as an input for the second tool.

Fireline QAQC: Using a single NIFC wildfire perimeter as an input, select the relevant calendar year and run the tool. Once the tool has ran, conduct visual QAQC to remove wrongly attributed firelines or geometric anomalies, such as a straight fireline with no vertices that span long distances.

Simplification (Optional): If needed, apply Tool 2B for a simplified dissolved fireline dataset.

Engagement Analysis: Utilize Tool 3 to attribute engagement statuses to QAQCed firelines. This will attribute “Held”, “Not Engaged”, and “Not Held” to firelines using a user provided buffer distance from the fire perimeter. A second output will be created that buffers the firelines so that they are suitable for overlay analysis. This step is optional as it is not necessary for FLE.

Metric Calculation: Apply Tool 4 using the perimeter and QAQCed firelines from tool 1 and 2 to calculate and analyze FLE metrics. The outputs will be in feature class and excel xls formats. 

For more information regarding the tools, please look at the tool descriptions or the description embedded in the python code itself.


### Limitations:
ArcGIS Pro Version: Users must have ArcGIS Pro version 3 or higher. The tools are designed to work within the functionalities of this software version and may not be compatible with earlier versions.
File Directory Structure: Proper formatting and naming of the file directory are crucial. 
Users must ensure that the directory structure and file naming conventions are correctly set up as per the toolkit's requirements. This is essential for the smooth operation and integration of the different tools in the toolkit.
A stable internet connection is required, especially for tools that download data from online sources or require data syncing. Interruptions in connectivity could lead to incomplete data processing or other errors.

For more information regarding fireline effectiveness please refer to the following research articles:
Evaluating fireline effectiveness across large wildfire events in north-central Washington State https://fireecology.springeropen.com/articles/10.1186/s42408-023-00167-6
A Geospatial Framework to Assess Fireline Effectiveness for Large Wildfires in the Western USA https://www.mdpi.com/2571-6255/3/3/43
Wildfire response performance measurement: Current and future directions https://www.fs.usda.gov/research/treesearch/56495


### Contributions:
This toolkit represents an ongoing effort to enhance fire management strategies through data-driven analysis, and community contributions are vital for its continuous improvement. Please note that the creator of this toolkit is not a professional coder, and therefore, errors may present themselves in the code. Additionally, the toolkit might produce some unnecessary outputs during its operation. We actively encourage the community to contribute towards optimizing and improving the code. If you have suggestions for enhancements, identify bugs, or find ways to streamline the processes to reduce unnecessary outputs, your input is greatly appreciated. Your expertise and insights are invaluable in refining this toolkit to better serve the needs of the wildfire research and management community.
Please reach out with your contributions, feedback, or suggestions to Alexander Arkowitz at aarkowitz@gmail.com or alexander.arkowitz@colostate.edu.

### Author Information:
Alexander Arkowitz, Geospatial Wildfire Research Associate IV, Colorado State University. Contractor, USFS Rocky Mountain Research Station
Email: aarkowitz@gmail.com, alexander.arkowitz@colostate.edu

### Acknowledgements:
Special thanks to Matt Thompson, my supervisor, for conceiving this idea and helping develop this workflow.  Gratitude also extends to Brad Pietruszka for his extensive knowledge in wildfire incident operations and data structure, and to Ben Gannon for his expertise in data processing and wildfire data.
