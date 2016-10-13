"""Create table that is used to populate left and right bike attributes for roads.
- Field and value translation for Salt Lake County data."""
import arcpy
from configs import Configs
from bikelanes_to_roads import *
from time import time


def isEmpty(fieldValue):
    """Return true for None or empty whitespace strings"""
    return fieldValue is None or str(fieldValue).strip() == ''


def joinBikeTypeFields(coverageTable, coverIdField, typeFields, bikeLanes):
    """Join the bike type to the coverage table."""
    arcpy.AddIndex_management(coverageTable.path, 'CoverId', 'coverIdIndex')
    arcpy.JoinField_management(coverageTable.path, 'CoverId',
                               bikeLanes.path, bikeLanes.ObjectIdField,
                               typeFields)


def translateBikeFieldsToDomain(coverageTable, bikelaneFields):
    """Translate bike types to CVDomain_OnStreetBike codes."""
    fields = ['BIKE_R', 'BIKE_L', 'RD_BIKE_NOTES', 'BIKE_STATUS']
    for f in fields:
        fieldLength = 50
        # if f == 'RD_BIKE_NOTES':
        #     fieldLength = 254
        arcpy.AddField_management(coverageTable.path, f, 'TEXT', field_length=fieldLength)

    fields.extend(bikelaneFields)
    # Roads bike field indices:
    leftI = fields.index('BIKE_L')
    rightI = fields.index('BIKE_R')
    roadNotesI = fields.index('RD_BIKE_NOTES')
    statusI = fields.index('BIKE_STATUS')
    # Salt Lake County bike lane field indices
    lExiI = fields.index('BIKE_L_EXI')
    lProI = fields.index('BIKE_L_PRO')
    rExiI = fields.index('BIKE_R_EXI')
    rProI = fields.index('BIKE_R_PRO')
    regionalI = fields.index('REGIONAL_P')
    slNotesI = fields.index('BIKE_NOTES')

    with arcpy.da.UpdateCursor(coverageTable.path, fields) as cursor:
        for row in cursor:
            if not isEmpty(row[lProI]) or not isEmpty(row[rProI]):
                row[leftI] = row[lProI]
                row[rightI] = row[rProI]
                row[roadNotesI] = '|'.join([row[lProI], row[rProI], row[regionalI], row[slNotesI]])[:50]
                row[statusI] = 'P'
                if row[regionalI].upper() == 'Y':
                    row[statusI] = None

            if not isEmpty(row[lExiI]):
                row[leftI] = row[lExiI]
                row[statusI] = 'E'
                if isEmpty(row[roadNotesI]):
                    row[roadNotesI] = row[slNotesI][:50]
            if not isEmpty(row[rExiI]):
                row[rightI] = row[rExiI]
                row[statusI] = 'E'
                if isEmpty(row[roadNotesI]):
                    row[roadNotesI] = row[slNotesI][:50]

            cursor.updateRow(row)

if __name__ == '__main__':
    dataDirectory = r'.\data'
    Configs.setupWorkspace(dataDirectory)
    totalTime = time()

    # User provided feature classes.
    fullSgidRoads = Feature(r'Database Connections\Connection to utrans.agrc.utah.gov.sde\UTRANS.TRANSADMIN.Centerlines_Edit',
                            'UTRANS.TRANSADMIN.StatewideStreets')
    bikeLanes = Feature(Configs.dataGdb,
                        'SLCountyBikeUpdate')
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
    # Analylize geometery to find roads that are covered by a bikelane.
    roadCoverageTable = getRoadCoverageTable(subsetLayer, bikeLanes, distFromBikeLanes)
    # Join and translate fields from bikeLanes to roadCoverageTable
    joinBikeTypeTime = time()
    bikeLaneFields = ['BIKE_L_EXI',
                      'BIKE_L_PRO',
                      'BIKE_R_EXI',
                      'BIKE_R_PRO',
                      'REGIONAL_P',
                      'BIKE_NOTES']
    joinBikeTypeFields(roadCoverageTable, 'CoverId', bikeLaneFields, bikeLanes)
    print 'Joined bike type fields: {}'.format(round(time() - joinBikeTypeTime, 3))

    translateTime = time()
    translateBikeFieldsToDomain(roadCoverageTable, bikeLaneFields)
    print 'translate fields: {}'.format(round(time() - translateTime, 3))

    print 'Completed: {}'.format(round(time() - totalTime, 3))
