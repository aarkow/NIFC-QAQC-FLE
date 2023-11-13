# NIFC-QAQC-FLE
Author Information:
Alexander Arkowitz
Geospatial Wildfire Research Associate IV, Colorado State University
Contractor, Rocky Mountain Research Station
Email: aarkowitz@gmail.com, alexander.arkowitz@colostate.edu

Overview:
This repository contains a suite of tools designed for wildfire data researchers and fire management professionals. 
These tools facilitate the creation of fireline engagement metrics, aiding in the evaluation and improvement of wildfire management strategies. 
The toolkit is instrumental in addressing the challenges of limited suppression effectiveness data collection and analysis,
 which has historically hindered the assessment of wildfire management decisions.

Background:
The increasing availability of spatially explicit fireline records enables the evaluation of containment strategies using 
fireline effectiveness (FLE) metrics. These metrics are based on measures like the length of the final wildfire perimeter 
and the performance of firelines (burned over, held, or not engaged). This toolkit aims to expand the application of FLE 
metrics beyond case studies, enhancing the understanding and evaluation of incident-level strategy effectiveness.

General Workflow:
Data Preparation: Start by using Tool 1 to ensure the integrity and accuracy of fire perimeter data.
Fireline QAQC: Use Tool 2 to process and quality-check fireline data from NIFC operations.
Simplification (Optional): If needed, apply Tool 2B for a simplified fireline dataset.
Engagement Analysis: Utilize Tool 3 to attribute engagement statuses and prepare data for overlay analysis.
Metric Calculation: Finally, apply Tool 4 to calculate and analyze FLE metrics, aiding in strategic decision-making.

Tool 1: 1_NIFC_Perimeters_QAQC.py
Usage: Conducts QAQC on NIFC public perimeter datasets to identify issues such as duplicate perimeters with different attribution.
Description: Downloads and analyzes fire perimeter data from the National Interagency Fire Center (NIFC), ensuring data integrity and accuracy. 
It identifies duplicate shapes and purges invalid entries, crucial for reliable analysis.

Tool 2: 2_NIFC_Fireline_QAQC
Usage: Processes NIFC Operations fireline data, requiring visual inspection and QAQC on the output.
Description: A Python script for ArcGIS, handling the downloading, formatting, and quality control of fire-related datasets.
It focuses on ensuring consistency in attributes like IRWIN IDs and incident names and removing duplicates and irrelevant data.

Tool 2B: 2B_NIFC_Fireline_Reprocessing.py
Usage: Generates a simplified version of the QAQC fireline dataset post-manual edits.
Description: Dissolves and removes duplicate firelines based on shape, Incident Name, Line Type, and IRWIN ID, offering a streamlined dataset for analysis.

Tool 3: 3_Fireline_EngagementOverlay.py
Usage: Attributes engagement status to QAQCed firelines and generates buffered fireline polygons for overlay analysis.
Description: Integrates NIFC Wildfire perimeter and QAQCed fireline datasets to create line and polygon feature classes. 
It attributes engagement status and ranks treatment efforts for analysis.

Tool 4: 4_FLEMetrics
Usage: Calculates various FLE metrics to assess fireline engagement and suppression strategies.
Description: Automates the computation of metrics like Holding Ratio, Treatment Ratio, and Engagement Ratio. 
Includes flagging mechanisms for anomalies and facilitates efficient post-incident analysis.

Limitations:
ArcGIS Pro Version: Users must have ArcGIS Pro version 3 or higher. The tools are designed to work within the functionalities
of this software version and may not be compatible with earlier versions.
File Directory Structure: Proper formatting and naming of the file directory are crucial. 
Users must ensure that the directory structure and file naming conventions are correctly set up as per the toolkit's requirements. 
This is essential for the smooth operation and integration of the different tools in the toolkit.
Stable Internet Connection: A stable internet connection is required, especially for tools that download data from online sources or require data syncing.
Interruptions in connectivity could lead to incomplete data processing or other errors.

Contributions:
This toolkit represents an ongoing effort to enhance fire management strategies through data-driven analysis, and community contributions
are vital for its continuous improvement. Please note that the creator of this toolkit is not a professional coder, and therefore,
errors may present themselves in the code. Additionally, the toolkit might produce some unnecessary outputs during its operation.
We actively encourage the community to contribute towards optimizing and improving the code. If you have suggestions for enhancements,
identify bugs, or find ways to streamline the processes to reduce unnecessary outputs, your input is greatly appreciated. 
Please reach out with your contributions, feedback, or suggestions to Alexander Arkowitz at aarkowitz@gmail.com or alexander.arkowitz@colostate.edu.
Your expertise and insights are invaluable in refining this toolkit to better serve the needs of the wildfire research and management community.

Acknowledgements:
Special thanks to Matt Thompson, my supervisor, for conceiving this idea and helping develop this workflow. 
Gratitude also extends to Brad Pietruszka for his extensive knowledge in wildfire incident operations and data structure, 
and to Ben Gannon for his expertise in data processing and wildfire data.
