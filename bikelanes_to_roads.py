"""Add bike left and right attribute to roads from bike lane data."""
import arcpy
import os
from time import strftime
from time import time
from operator import itemgetter

uniqueRunNum = strftime("%Y%m%d_%H%M%S")


class OtherFeature(object):
    """Accumulate information about features that cover lines."""

    def __init__(self, featureId):
        """constructor."""
        self.id = featureId
        self.coveragePercent = 0
        self.intersections = 0
        self.joinDistSum = 0

    def __str__(self):
        """Override str."""
        return '{}: coverage: {} interx: {}'.format(self.id,
                                                    self.coveragePercent,
                                                    self.intersections)


class LineCoverage (object):
    """Create and store coverage percentages."""

    def __init__(self, lineId, otherId, linePos):
        """constructor."""
        self.lineId = lineId
        self.lastOtherId = None
        self.lastOtherPos = linePos
        self.others = {}  # {'OtherId': 'accumulation'}

    def accumulateCoverage(self, otherId, currentLinePos, joinDist):
        """Accumulate coverage percentage for id."""

        if self.lastOtherId == otherId:  # Check if otherId is a continuation of the last id seen
            self.others[otherId].coveragePercent += float(currentLinePos) - self.lastOtherPos
        elif otherId not in self.others:
            self.others[otherId] = OtherFeature(otherId)

        self.others[otherId].intersections += 1
        self.others[otherId].joinDistSum += joinDist
        self.lastOtherId = otherId
        self.lastOtherPos = currentLinePos

    def getCoverageRows(self):
        """Get rows for the coverage table output."""
        tempRows = []
        for id in self.others:
            coverFeature = self.others[id]
            tempRows.append((self.lineId,
                             coverFeature.id,
                             round(coverFeature.joinDistSum, 4),
                             coverFeature.coveragePercent,
                             coverFeature.intersections))

        return tempRows


class Table (object):
    """Store usefull table information."""

    def __init__(self, workspace, name):
        """constructor."""
        self.workspace = workspace
        self.name = name
        self.path = os.path.join(workspace, name)
        self.ObjectIdField = arcpy.Describe(self.path).OIDFieldName

    @staticmethod
    def createTable(workspace, name, fieldList=[]):
        """Create an ArcGIS table and retrun a table object."""
        arcpy.CreateTable_management(workspace,
                                     name)
        tempFeature = Table(workspace, name)

        if len(fieldList) > 0:
            for field in fieldList:
                name = field[0]
                fieldType = field[1]
                arcpy.AddField_management(tempFeature.path,
                                          name,
                                          fieldType)

        return tempFeature


class Feature (object):
    """Store usefull feature class information."""

    def __init__(self, workspace, name, spatialRef=None):
        """constructor."""
        self.workspace = workspace
        self.name = name
        self.path = os.path.join(workspace, name)
        self.ObjectIdField = arcpy.Describe(self.path).OIDFieldName
        self.spatialReference = spatialRef
        if self.spatialReference is None:
            self.spatialReference = arcpy.Describe(self.path).spatialReference

    @staticmethod
    def createFeature(workspace, name, spatialRef, geoType, fieldList=[]):
        """Create a feature class and retrun a feature object."""
        arcpy.CreateFeatureclass_management(workspace,
                                            name,
                                            geoType,
                                            spatial_reference=spatialRef)
        tempFeature = Feature(workspace, name, spatialRef)

        if len(fieldList) > 0:
            for field in fieldList:
                name = field[0]
                fieldType = field[1]
                if name == 'SHAPE@':
                    continue
                arcpy.AddField_management(tempFeature.path,
                                          name,
                                          fieldType)

        return tempFeature

    @staticmethod
    def createFeatureFromLayer(workspace, name, layer):
        """Create a feature class and retrun a feature object."""
        tempFeature = Feature(workspace, name, arcpy.Describe(layer).spatialReference)
        arcpy.CopyFeatures_management(layer, os.path.join(workspace, name))

        return tempFeature


def createBikeLaneRoadCoverage(roadPointsWithBikeFields):
    """Use the join fields from road point to determine bike lane that covers road segement."""
    fields = ['LineId', 'LinePos', 'NEAR_FID', 'NEAR_DIST', 'Type', 'Stat_2015']
    rows = None
    lineCoverages = {}

    coverageFields = [('LineId', 'LONG'),
                      ('CoverId', 'LONG'),
                      ('JoinDistSum', 'DOUBLE'),
                      ('Precent', 'FLOAT'),
                      ('Interx', 'SHORT')]
    coverageTable = Table.createTable(outputWorkspace,
                                      'LineCoverage_' + uniqueRunNum,
                                      coverageFields)
    tableCursor = arcpy.da.InsertCursor(coverageTable.path,
                                        [x[0] for x in coverageFields])

    with arcpy.da.SearchCursor(roadPointsWithBikeFields.path, fields) as cursor:
        rows = sorted(cursor, key=itemgetter(0, 1))

    lC = None
    for row in rows:

        lineId, linePos, otherId, otherDist, bikeType, bikeStat = row

        if lineId not in lineCoverages:
            lineCoverages[lineId] = LineCoverage(lineId, otherId, linePos)
            if lC is not None:  # Popluate the line coverage table.
                for row in lC.getCoverageRows():
                    tableCursor.insertRow(row)

        lC = lineCoverages[lineId]
        lC.accumulateCoverage(otherId, linePos, otherDist)

    # Insert last row in coverage table
    for row in lC.getCoverageRows():
        tableCursor.insertRow(row)
    del tableCursor

    return coverageTable


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


def joinPointsAndBikelanes(roadPoints, bikeLanes, bikeLaneFields, nearSearchRadius):
    """Join relevent fields from bikeLanes to road points."""
    # Near adds NEAR_FID and NEAR_DIST to roadPoints
    nearTime = time()
    arcpy.Near_analysis(roadPoints.path, bikeLanes.path, nearSearchRadius)
    print 'joinPointsAndBikelanes-Near: {}'.format(time() - nearTime)
    joinFieldTime = time()
    arcpy.AddIndex_management(triPoint.path, 'NEAR_FID', 'nearIndex')
    # arcpy.AddIndex_management(bikeLanes.path, bikeLanes.ObjectIdField, 'bikeOidIndex')
    arcpy.JoinField_management(roadPoints.path,
                               'NEAR_FID',
                               bikeLanes.path,
                               bikeLanes.ObjectIdField,
                               bikeLaneFields)
    print 'joinPointsAndBikelanes-Join: {}'.format(time() - joinFieldTime)


def createTriPointFeature(lineLayer):
    """Create a feature class of first last and mid points for each line."""
    triPointFields = [('LineId', 'LONG'),
                      ('LinePos', 'FLOAT'),
                      ('SHAPE@', 'geometery')]
    triPoint = Feature.createFeature(tempWorkspace,
                                     'roadTriPoint',
                                     arcpy.Describe(lineLayer).spatialReference,
                                     'POINT',
                                     triPointFields)

    triCursor = arcpy.da.InsertCursor(triPoint.path,
                                      [x[0] for x in triPointFields])
    with arcpy.da.SearchCursor(lineLayer, ['OID@', 'SHAPE@']) as cursor:
        for row in cursor:
            oid, line = row
            triCursor.insertRow((oid,
                                 0,
                                 arcpy.PointGeometry(line.firstPoint,
                                                     triPoint.spatialReference)))
            triCursor.insertRow((oid,
                                 1,
                                 arcpy.PointGeometry(line.lastPoint,
                                                     triPoint.spatialReference)))
            triCursor.insertRow((oid,
                                 0.5,
                                 line.positionAlongLine(0.5, True)))

    del triCursor

    return triPoint


def createRoadSubset(fullSgid, bikeLanes):
    distFromBikeLanes = 12

    subsetLayer = 'roadsCloseToBikelanes'
    arcpy.MakeFeatureLayer_management(fullSgid.path, subsetLayer)
    arcpy.SelectLayerByLocation_management(subsetLayer,
                                           'WITHIN_A_DISTANCE',
                                           bikeLanes.path,
                                           distFromBikeLanes)

    return Feature.createFeatureFromLayer(tempWorkspace,
                                          'RoadsWithin{}'.format(distFromBikeLanes),
                                          subsetLayer)


if __name__ == '__main__':
    totalTime = time()
    global outputWorkspace
    global tempWorkspace
    global dataGdb
    print 'Run {}'.format(uniqueRunNum)
    # Workspaces
    dataGdb = r'C:\GisWork\BikeLanesToRoads\SourceData.gdb'
    outputWorkspace = r'C:\GisWork\BikeLanesToRoads\OutputResults.gdb'
    # Create a temp unique temp workspace for this run
    tempWorkspace = r'C:\GisWork\BikeLanesToRoads\temp'
    arcpy.CreateFileGDB_management(tempWorkspace,
                                   'run_' + uniqueRunNum)
    tempWorkspace = os.path.join(tempWorkspace, 'run_' + uniqueRunNum + '.gdb')
    # User provided feature classes.
    fullSgidRoads = Feature(r'Database Connections\Connection to utrans.agrc.utah.gov.sde\UTRANS.TRANSADMIN.Centerlines_Edit',
                            'UTRANS.TRANSADMIN.StatewideStreets')
    bikeLanes = Feature(dataGdb,
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

    triPointTime = time()
    triPoint = createTriPointFeature(subsetLayer)
    print 'Created 3 points along subset roads: {}'.format(round(time() - triPointTime, 3))

    joinNearTime = time()
    bikeLaneFields = ['Type', 'Stat_2015']
    joinPointsAndBikelanes(triPoint, bikeLanes, bikeLaneFields, distFromBikeLanes)
    print 'Joined bikeLane fields to road points: {}'.format(round(time() - joinNearTime, 3))

    coverageTime = time()
    roadCoverageTable = createBikeLaneRoadCoverage(triPoint)
    print 'Created line coverage table: {}'.format(round(time() - coverageTime, 3))

    joinBikeTypeTime = time()
    joinBikeTypeFields(roadCoverageTable, 'CoverId', ['Type', 'Stat_2015'], bikeLanes)
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
