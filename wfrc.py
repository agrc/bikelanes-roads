"""Create table that is used to populate left and right bike attributes for roads.
- Field and value translation for Wasatch Front regional counsel data."""
import arcpy
from configs import Configs
from bikelanes_to_roads import *
from time import time


def joinBikeTypeFields(coverageTable, coverIdField, typeFields, bikeLanes):
    """Join the bike type to the coverage table."""
    arcpy.AddIndex_management(coverageTable.path, 'CoverId', 'coverIdIndex')
    arcpy.JoinField_management(coverageTable.path, 'CoverId',
                               bikeLanes.path, bikeLanes.ObjectIdField,
                               typeFields)


def translateBikeFieldsToDomain(coverageTable, typeField, typeCodes, statusField, statusCodes):
    """Translate bike types to CVDomain_OnStreetBike codes."""
    typeDomainField = 'BikeTypeCode'
    arcpy.AddField_management(coverageTable.path, typeDomainField, 'TEXT', field_length=5)
    with arcpy.da.UpdateCursor(coverageTable.path, [typeField, typeDomainField, statusField]) as cursor:
        for row in cursor:
            typeValue = row[0]
            if typeValue is not None:
                typeValue = typeValue.lower().strip()
                if typeValue in typeCodes:
                    row[1] = typeCodes[typeValue]

            statusValue = row[2]
            if statusValue is not None:
                statusValue = statusValue.lower().strip()
                if statusValue in statusCodes:
                    row[2] = statusCodes[statusValue]

            cursor.updateRow(row)

if __name__ == '__main__':
    dataDirectory = r'.\data'
    Configs.setupWorkspace(dataDirectory)
    totalTime = time()
    # User provided feature classes.
    fullSgidRoads = Feature(r'Database Connections\Connection to utrans.agrc.utah.gov.sde\UTRANS.TRANSADMIN.Centerlines_Edit',
                            'UTRANS.TRANSADMIN.StatewideStreets')
    bikeLanes = Feature(Configs.dataGdb,
                        'WFRC_BikeLanes')
    distFromBikeLanes = 12  # distance to limit the road layer. Chosen after exploratory analysis.
    # Select road within a distance from bike lanes.
    subsetLayer = 'roadsCloseToBikeLanes'
    selectTime = time()
    arcpy.MakeFeatureLayer_management(fullSgidRoads.path, subsetLayer)
    arcpy.SelectLayerByLocation_management(subsetLayer,
                                           'WITHIN_A_DISTANCE',
                                           bikeLanes.path,
                                           distFromBikeLanes)
    print 'Created subset of SGID roads: {}'.format(round(time() - selectTime, 3))
    roadCoverageTable = getRoadCoverageTable(subsetLayer, bikeLanes, distFromBikeLanes)
    # Join and translate fields from bikeLanes to roadCoverageTable
    joinBikeTypeTime = time()
    bikeLaneFields = ['Type', 'Stat_2015']
    joinBikeTypeFields(roadCoverageTable, 'CoverId', bikeLaneFields, bikeLanes)
    print 'Joined bike type fields: {}'.format(round(time() - joinBikeTypeTime, 3))

    typeCodes = {
        'bike lane': '2C',
        'shared use path': '2C',
        'shared lane': '3B',
        'locally identified corridor': '3C',
        'shoulder bikeway': '2C',
        'category 1': '1',
        'category 3': '3',
        'grade separated bike lane': '1A',
        'unknown': '2C',
        '': '2C'
    }
    statusCodes = {
        'proprosed': 'P',
        'existing': 'E'
    }
    translateTime = time()
    translateBikeFieldsToDomain(roadCoverageTable, 'Type', typeCodes, 'Stat_2015', statusCodes)
    print 'translate fields: {}'.format(round(time() - translateTime, 3))

    print 'Completed: {}'.format(round(time() - totalTime, 3))
