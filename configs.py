"""Global settings and paths."""
import os
import arcpy
from time import strftime


class Configs(object):
    uniqueRunNum = None
    outputWorkspace = None
    tempWorkspace = None
    dataGdb = None

    @staticmethod
    def setupWorkspace(dataDirectory):
        """Setup workspaces for temp features and outputs."""

        if Configs.uniqueRunNum is None:
            Configs.uniqueRunNum = strftime("%Y%m%d_%H%M%S")
            print 'Run {}'.format(Configs.uniqueRunNum)
        if Configs.outputWorkspace is None and Configs.tempWorkspace is None and Configs.dataGdb is None:
            # Workspaces
            Configs.dataGdb = os.path.join(dataDirectory, 'SourceData.gdb')
            Configs.outputWorkspace = os.path.join(dataDirectory, 'OutputResults.gdb')
            # Create a temp unique temp workspace for this run
            tempDir = os.path.join(dataDirectory, 'temp')
            arcpy.CreateFileGDB_management(tempDir,
                                           'run_' + Configs.uniqueRunNum)
            Configs.tempWorkspace = os.path.join(tempDir, 'run_' + Configs.uniqueRunNum + '.gdb')
