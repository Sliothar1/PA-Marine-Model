
Data extraction “IrishHeatwaves”
Extraction performed by Pierre Hélaouët
07/09/2026.
DOI: 10.17031/6a9e6f4a00142
Web page: https://doi.mba.ac.uk/data/3793
Note: As always, this dataset has been carefully built and checked accordingly. However, it is the user’s responsibility to perform his own verifications.
Quick description of the dataset
1 – The dataset contains 7 files:
“CPR_Data_IrishHeatwaves_04062026.docx”: This document
“CPR_IrishHeatwaves_ControlMap_04062026.png”: 
Map representing the selected samples, in the area from 49°N to 61°N; -16°E to 0°E, from January 1982 to December 2022 (41884 samples)
“CPR_IrishHeatwaves_Data_04092026.csv”: For all samples available, mean abundance data for all selected groups (4 groups) as well as Phytoplankton Colour Index (PCI).
large (≥2mm) copepods, 44 taxa, see CPR_IrishHeatwaves_List_LargeCopepods_04092026.csv 
small (&lt;2mm) copepods, 33 taxa, see CPR_IrishHeatwaves_List_SmallCopepods_04092026.csv
diatoms, 61 taxa, see CPR_IrishHeatwaves_List_Diatoms_04092026.csv
dinoflagellates, 44 taxa, see CPR_IrishHeatwaves_List_Dinoflagellates_04092026.csv
PCI
Rows: All samples for the selected area (41884 samples).
Column 1: “SampleId”: Unique sample id. For instance: “240B--27” corresponds to the 27th sample for the 240th transect on the B route.
Columns from 2 to 8: Spatio-temporal coordinates for each sample (Time in UTC) 
Columns from 9 to 13: Mean abundance data for all selected groups
Note 1: A CPR sample corresponds to 3m3 of filtered water.
Note 2: To maintain a constant taxa list across the selected period, only taxa constantly analysed since 1982 were retained (see Column 5 in associated list of taxa (e.g., CPR_IrishHeatwaves_List_LargeCopepods_04092026.csv).
Note 3: Phytoplankton Colour Index (PCI) corresponds to the greenness of the silk and is associated to a semi-logarithmic scale as follow:
no colour = 0
very pale green = 1
pale green = 2
green = 6.5
“CPR_IrishHeatwaves_List_LageCopepods_04062026.csv”: List of large copepods (≥2mm)
Rows: All selected taxa (44 taxa).
Column 1 “Accepted_ID”: Unique identifier used by the CPR survey
Column 2 "Taxon_Name”: Unique name used by the CPR survey.
Column 3 " WoRMS_Name”: Name used by WoRMS corresponding to the “Aphia_ID”.
Column 4 " Aphia_ID”: Identifier used by WoRMS
Column 5 "DRI”: Date of Routine Identification. Before that date, un taxon was not on our routine taxa list. For a given taxon, abundances associated with samples taken before the DRI are set to a NaN (Not A Number).
Column 6 to 12: Taxonomic information (simplified) for each taxa.
“CPR_IrishHeatwaves_List_SmallCopepods_04062026.csv”: List of small copepods (&lt;2mm).
Rows: All selected taxa (33 taxa).
Note: Same architecture as “CPR_IrishHeatwaves_List_LageCopepods_04062026.csv”.
“CPR_IrishHeatwaves_List_Diatoms_04062026.csv”: List phytoplankton (61 taxa).
Note: Same architecture as “CPR_IrishHeatwaves_List_LageCopepods_04062026.csv”.
“CPR_IrishHeatwaves_List_Dinoflagellates_04062026.csv”: List phytoplankton (44 taxa).
Note: Same architecture as “CPR_IrishHeatwaves_List_LageCopepods_04062026.csv”.
