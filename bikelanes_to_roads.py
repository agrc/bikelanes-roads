"""Find coverage information for bike lane data and roads."""
import arcpy
import os
from configs import Configs
from time import time
from operator import itemgetter


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
            tempRows.append([self.lineId,
                             coverFeature.id,
                             round(coverFeature.joinDistSum, 4),
                             coverFeature.coveragePercent,
                             coverFeature.intersections])

        # Add valid, unique, id full coverage field
        validCoverIds = set([r[1] for r in tempRows])
        validCoverIds.discard(-1)
        if len(validCoverIds) == 3:  # 3 is used because 3 points are created per road line.
            for r in tempRows:
                r.append(1)
        else:
            for r in tempRows:
                r.append(0)
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
    fields = ['LineId', 'LinePos', 'NEAR_FID', 'NEAR_DIST']  # , 'Type', 'Stat_2015']
    rows = None
    lineCoverages = {}

    coverageFields = [('LineId', 'LONG'),
                      ('CoverId', 'LONG'),
                      ('JoinDistSum', 'DOUBLE'),
                      ('Precent', 'FLOAT'),
                      ('Interx', 'SHORT'),
                      ('AllUniqueIds', 'SHORT')]
    coverageTable = Table.createTable(Configs.outputWorkspace,
                                      'LineCoverage_' + Configs.uniqueRunNum,
                                      coverageFields)
    tableCursor = arcpy.da.InsertCursor(coverageTable.path,
                                        [x[0] for x in coverageFields])

    with arcpy.da.SearchCursor(roadPointsWithBikeFields.path, fields) as cursor:
        rows = sorted(cursor, key=itemgetter(0, 1))

    lC = None
    for row in rows:

        lineId, linePos, otherId, otherDist = row  # , bikeType, bikeStat = row

        if lineId not in lineCoverages:
            lineCoverages[lineId] = LineCoverage(lineId, otherId, linePos)
            if lC is not None:  # Popluate the line coverage table.
                for lcRow in lC.getCoverageRows():
                    tableCursor.insertRow(lcRow)

        lC = lineCoverages[lineId]
        lC.accumulateCoverage(otherId, linePos, otherDist)

    # Insert last row in coverage table
    for lcRow in lC.getCoverageRows():
        tableCursor.insertRow(lcRow)
    del tableCursor

    return coverageTable


def nearPointsAndBikelanes(roadPoints, bikeLanes, nearSearchRadius):
    """Join relevent fields from bikeLanes to road points."""
    # Near adds NEAR_FID and NEAR_DIST to roadPoints
    nearTime = time()
    arcpy.Near_analysis(roadPoints.path, bikeLanes.path, nearSearchRadius)
    print 'joinPointsAndBikelanes-Near: {}'.format(time() - nearTime)


def createTriPointFeature(lineLayer):
    """Create a feature class of first last and mid points for each line."""
    triPointFields = [('LineId', 'LONG'),
                      ('LinePos', 'FLOAT'),
                      ('SHAPE@', 'geometery')]
    triPoint = Feature.createFeature(Configs.tempWorkspace,
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

    return Feature.createFeatureFromLayer(Configs.tempWorkspace,
                                          'RoadsWithin{}'.format(distFromBikeLanes),
                                          subsetLayer)


def getRoadCoverageTable(subsetLayer, bikeLanes, distFromBikeLanes):
    triPointTime = time()
    triPoint = createTriPointFeature(subsetLayer)
    print 'Created 3 points along subset roads: {}'.format(round(time() - triPointTime, 3))

    joinNearTime = time()
    nearPointsAndBikelanes(triPoint, bikeLanes, distFromBikeLanes)
    print 'Joined bikeLane fields to road points: {}'.format(round(time() - joinNearTime, 3))

    coverageTime = time()
    roadCoverageTable = createBikeLaneRoadCoverage(triPoint)
    print 'Created line coverage table: {}'.format(round(time() - coverageTime, 3))

    return roadCoverageTable

if __name__ == '__main__':
    totalTime = time()
    global outputWorkspace
    global tempWorkspace
    global dataGdb
    print 'Run {}'.format(Configs.uniqueRunNum)
    # Workspaces
    dataDirectory = r'C:\GisWork\BikeLanesToRoads'
    dataGdb = os.path.join(dataDirectory, 'SourceData.gdb')
    outputWorkspace = os.path.join(dataDirectory, 'OutputResults.gdb')
    # Create a temp unique temp workspace for this run
    tempWorkspace = os.path.join(dataDirectory, 'temp')
    arcpy.CreateFileGDB_management(tempWorkspace,
                                   'run_' + Configs.uniqueRunNum)
    tempWorkspace = os.path.join(tempWorkspace, 'run_' + Configs.uniqueRunNum + '.gdb')
    # User provided feature classes.
    fullSgidRoads = Feature(r'Database Connections\Connection to utrans.agrc.utah.gov.sde\UTRANS.TRANSADMIN.Centerlines_Edit',
                            'UTRANS.TRANSADMIN.StatewideStreets')
    bikeLanes = Feature(dataGdb,
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

    triPointTime = time()
    triPoint = createTriPointFeature(subsetLayer)
    print 'Created 3 points along subset roads: {}'.format(round(time() - triPointTime, 3))

    joinNearTime = time()
    nearPointsAndBikelanes(triPoint, bikeLanes, distFromBikeLanes)
    print 'Joined bikeLane fields to road points: {}'.format(round(time() - joinNearTime, 3))

    coverageTime = time()
    roadCoverageTable = createBikeLaneRoadCoverage(triPoint)
    print 'Created line coverage table: {}'.format(round(time() - coverageTime, 3))

    print 'Completed: {}'.format(round(time() - totalTime, 3))
