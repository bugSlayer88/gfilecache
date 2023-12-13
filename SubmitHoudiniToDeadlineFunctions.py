#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function

import json
import os
import re
import subprocess
import sys
import time

import hou

PADDED_NUMBER_REGEX = re.compile( "([0-9]+)", re.IGNORECASE )

# TODO: This function is a duplicate from CallDeadlineCommand.py. Once we're a full major version
# from Deadline 10 we can remove this since the client script will have the be updated.
def GetDeadlineCommand():
    deadlineBin = ""
    try:
        deadlineBin = os.environ['DEADLINE_PATH']
    except KeyError:
        #if the error is a key error it means that DEADLINE_PATH is not set. however Deadline command may be in the PATH or on OSX it could be in the file /Users/Shared/Thinkbox/DEADLINE_PATH
        pass

    # On OSX, we look for the DEADLINE_PATH file if the environment variable does not exist.
    if deadlineBin == "" and  os.path.exists( "/Users/Shared/Thinkbox/DEADLINE_PATH" ):
        with open( "/Users/Shared/Thinkbox/DEADLINE_PATH" ) as f:
            deadlineBin = f.read().strip()

    deadlineCommand = os.path.join(deadlineBin, "deadlinecommand")

    return deadlineCommand

# TODO: This function is a duplicate from CallDeadlineCommand.py. Once we're a full major version
# from Deadline 10 we can remove this since the client script will have the be updated.
def CallDeadlineCommand( arguments, hideWindow=True, readStdout=True ):
    deadlineCommand = GetDeadlineCommand()
    startupinfo = None
    creationflags = 0
    if os.name == 'nt':
        if hideWindow:
            # Python 2.6 has subprocess.STARTF_USESHOWWINDOW, and Python 2.7 has subprocess._subprocess.STARTF_USESHOWWINDOW, so check for both.
            if hasattr( subprocess, '_subprocess' ) and hasattr( subprocess._subprocess, 'STARTF_USESHOWWINDOW' ):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess._subprocess.STARTF_USESHOWWINDOW
            elif hasattr( subprocess, 'STARTF_USESHOWWINDOW' ):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        else:
            # still show top-level windows, but don't show a console window
            CREATE_NO_WINDOW = 0x08000000   #MSDN process creation flag
            creationflags = CREATE_NO_WINDOW

    arguments.insert( 0, deadlineCommand )

    # Specifying PIPE for all handles to workaround a Python bug on Windows. The unused handles are then closed immediately afterwards.
    proc = subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo, creationflags=creationflags)

    output = ""
    if readStdout:
        output, errors = proc.communicate()

    if sys.version_info[0] > 2 and type(output) == bytes:
        output = output.decode()

    return output

def GetJobIdFromSubmission( submissionResults ):
    jobId = ""
    for line in submissionResults.split():
        if line.startswith( "JobID=" ):
            jobId = line.replace( "JobID=", "" ).strip()
            break

    return jobId

def SaveScene():
    if hou.hipFile.hasUnsavedChanges():
        if hou.ui.displayMessage( "The scene has unsaved changes and must be saved before the job can be submitted.\nDo you wish to save?", buttons=( "Yes" , "No" ), title="Submit Houdini To Deadline" ) == 0:
            hou.hipFile.save()
        else:
            return False

    return True

def GetOutputPath( node ):
    outputFile = ""
    nodeType = node.type().description()
    category = node.type().category().name()

    #Figure out which type of node is being rendered
    if nodeType == "Geometry" or nodeType == "Filmbox FBX" or ( nodeType == "ROP Output Driver" and category == "Sop" ):
        outputFile = node.parm( "sopoutput" )
    elif nodeType == "Composite":
        outputFile = node.parm( "copoutput" )
    elif nodeType == "Channel":
        outputFile = node.parm( "chopoutput" )
    elif nodeType == "Dynamics" or ( nodeType == "ROP Output Driver" and category == "Dop" ):
        outputFile = node.parm( "dopoutput" )
    elif nodeType == "Alfred":
        outputFile = node.parm( "alf_diskfile")
    elif nodeType == "RenderMan" or nodeType == "RenderMan RIS":
        outputFile = node.parm( "ri_display" )
    elif nodeType == "Redshift":
        outputFile = node.parm( "RS_outputFileNamePrefix" )
    elif nodeType == "Mantra":
        outputFile = node.parm( "vm_picture" )
    elif nodeType == "Wedge":
        driverNode = node.node( node.parm( "driver" ).eval() )
        if driverNode:
            outputFile = GetOutputPath(driverNode)
    elif nodeType == "Arnold":
        outputFile = node.parm("ar_picture")
    elif nodeType == "HQueue Simulation":
        innerNode = node.node( node.parm( "hq_driver" ).eval() )
        if innerNode:
            outputFile = GetOutputPath( innerNode )
    elif nodeType == "ROP Alembic Output":
        outputFile = node.parm( "filename" )
    elif nodeType == "Redshift":
        outputFile = node.parm( "RS_outputFileNamePrefix" )
    elif nodeType == "Alembic":
        outputFile = node.parm( "filename" )
    elif nodeType == "Shotgun Mantra":
        outputFile = node.parm( "sgtk_vm_picture" )
    elif nodeType == "Shotgun Alembic":
        outputFile = node.parm( "filename" )
    elif nodeType == "Bake Texture":
        outputFile = node.parm("vm_uvoutputpicture1")
    elif nodeType == "OpenGL":
        outputFile = node.parm("picture")
    elif nodeType == "Octane":
        outputFile = node.parm("HO_img_fileName")
    elif nodeType == "Fetch":
        innerNode = node.node( node.parm( "source" ).eval() )
        if innerNode:
            outputFile = GetOutputPath( innerNode )
    elif is_vray_renderer_node( node ):
        outputFile = node.parm( "SettingsOutput_img_file_path" )


    #Check if outputFile could "potentially" be valid. ie. Doesn't allow Houdini's "ip"
    # or "md" values to be overridden, but silliness like " /*(xc*^zx$*asdf " would be "valid")
    if outputFile and not os.path.isabs( outputFile.eval() ):
        outputFile = "COMMAND"

    return outputFile

def GetExportPath( node ):
    ifdFile = None
    nodeType = node.type().description()

    # Ensures the proper Take is selected for each ROP to retrieve the correct ifd
    try:
        ropTake = hou.takes.findTake( node.parm( "take" ).eval() )
        if ropTake is not None:
            hou.takes.setCurrentTake( ropTake )
    except AttributeError:
        # hou object doesn't always have the 'takes' attribute
        pass

    if nodeType == "Mantra" and node.parm( "soho_outputmode" ).eval():
        ifdFile = node.parm( "soho_diskfile" )
    elif nodeType == "Alfred":
        ifdFile = node.parm( "alf_diskfile")
    elif ( nodeType == "RenderMan" or nodeType == "RenderMan RIS" ):
        pre_ris22 = node.parm( "rib_outputmode" ) and node.parm( "rib_outputmode" ).eval()
        ris22 = node.parm( "diskfile" ) and node.parm( "diskfile" ).eval()
        if pre_ris22 or ris22:
            ifdFile = node.parm( "soho_diskfile" )
    elif nodeType == "Redshift" and node.parm( "RS_archive_enable" ).eval():
        ifdFile = node.parm( "RS_archive_file" )
    elif nodeType == "Wedge" and node.parm( "driver" ).eval():
        ifdFile = GetExportPath( node.node(node.parm( "driver" ).eval()) )
    elif nodeType == "Arnold":
        ifdFile = node.parm( "ar_ass_file" )
    elif nodeType == "Alembic" and node.parm( "use_sop_path" ).eval():
        ifdFile = node.parm( "sop_path" )
    elif nodeType == "Shotgun Mantra" and node.parm( "soho_outputmode" ).eval():
        ifdFile = node.parm( "sgtk_soho_diskfile" )
    elif nodeType == "Shotgun Alembic" and node.parm( "use_sop_path" ).eval():
        ifdFile = node.parm( "sop_path" )
    elif is_vray_renderer_node( node ):
        ifdFile = node.parm( "render_export_filepath" )

    return ifdFile

def NodeSupportsTiles( node ):
    supportedTypes = [ "ifd", "arnold", "rib", "ris" ]
    nodeType = node.type().name()

    return ( nodeType in supportedTypes )

def WedgeTasks( wedgeNode ):
    numTasks = 1
    
    if wedgeNode.type().description() == "Wedge":
        wedgeMethod = wedgeNode.parm("wedgemethod").evalAsString()
        if wedgeMethod == "channel":
            numParams = wedgeNode.parm("wedgeparams").eval()
            random = wedgeNode.parm("random").eval()

            if random:
                # We're using the random settings
                numRandom = wedgeNode.parm("numrandom").eval()
                numTasks = numRandom * numParams
            else:
                # Using the number wedge params to determine task count
                for i in range(1, numParams+1):
                    numTasks = numTasks * wedgeNode.parm("steps"+str(i)).eval()
        
        elif wedgeMethod == "take":
            takename = wedgeNode.parm("roottake").eval()
            parentTake = hou.takes.findTake(takename)
            if parentTake:
                children = parentTake.children()
                numTasks = len(children)
            
    return numTasks

def is_vray_renderer_node( node ):
    """
    This seems to be the safest way to check a nodes type if we're not writing
    object-oriented code.  It allows us to define the matching string in a single place
    :param node: The node we're checking the type of
    :return: whether the node is a V-Ray Render node
    """
    VRayNodeType = "Driver/vray_renderer"
    return node.type().nameWithCategory() == VRayNodeType

def isExportJob( node, jobProperties ):
    """
    determines whether the given node is being exported
    :param node: The node which will be exported or rendered
    :param jobProperties: The current job's properties, which has values for whether a dependent job will be submitted
    :return: Whether an export job will be submitted
    """
    nodeType = node.type().description()

    if nodeType == "Mantra":
        return jobProperties.get( "mantrajob", False )
    elif nodeType == "Arnold":
        return jobProperties.get( "arnoldjob", False )
    elif nodeType == "RenderMan" or nodeType == "RenderMan RIS":
        return jobProperties.get( "rendermanjob", False )
    elif nodeType == "Redshift":
        return jobProperties.get( "redshiftjob", False )
    elif is_vray_renderer_node( node ):
        return jobProperties.get( "vrayjob", False )

    return False

def isExportLocal( node, jobProperties ):
    """
    Determines whether an export is local
    :param node: The node which will be exported or rendered
    :param jobProperties: The current job's properties, which has values for whether a the job will export locally
    :return: Whether an export job ius local
    """
    if isExportJob( node, jobProperties ):
        nodeType = node.type().description()

        if nodeType == "Mantra":
            return jobProperties.get( "mantralocalexport", False )
        elif nodeType == "Arnold":
            return jobProperties.get( "arnoldlocalexport", False )
        elif nodeType == "RenderMan" or nodeType == "RenderMan RIS":
            return jobProperties.get( "rendermanlocalexport", False )
        elif nodeType == "Redshift":
            return jobProperties.get( "redshiftlocalexport", False )
        elif is_vray_renderer_node( node ):
            return jobProperties.get( "vraylocalexport", False )

    return False

def IsPathLocal( path ):
    lowerPath = path.lower()
    return lowerPath.startswith( "c:" ) or lowerPath.startswith( "d:" ) or lowerPath.startswith( "e:" )

def hqueueSliceCount( node ):
    sliceCount = 1
    sliceType = node.parm("slice_type").evalAsString()
    if sliceType == "volume":
        slicesInX = node.parm("slicediv1").eval()
        slicesInY = node.parm("slicediv2").eval()
        slicesInZ = node.parm("slicediv3").eval()
        sliceCount = slicesInX * slicesInY * slicesInZ
    elif sliceType == "particle":
        sliceCount = node.parm("num_slices").eval()
    elif sliceType == "cluster":
        clusterNodeName = node.parm("hq_cluster_node").eval()
        if not clusterNodeName == "":
            clusterNode = node.node(clusterNodeName)
            sliceCount = clusterNode.parm("num_clusters").eval()
    elif sliceType == "None":
        pass

    return sliceCount

def single_export_file( node ):
    """
    Checks export name at two different frames, and determine's whether they're the same
    Currently only works with V-Ray render nodes
    :param node: The render node, which has an export filepath
    :return: True if only one file will be exported (by default)
    """
    return is_vray_renderer_node( node ) and node.parm("render_export_filepath").evalAtFrame(1) == node.parm("render_export_filepath").evalAtFrame(2)

def export_will_overwrite( node, jobProperties ):
    """
    Checks whether exports will overwrite when submitting an export job.  Currently only checks V-Ray
    :param node: The render node, which has an export filepath
    :jobProperties: jobProperties, including if there is an override and and what the frame range would be in that case
    :return: Whether exporting will overwrite in the current situation
    """
    # This is only implemented and tested for V-Ray
    isVray = is_vray_renderer_node( node )
    if not isVray:
        return False

    # if the export files are writing to different paths, they won't overwrite
    samePath = single_export_file( node )
    if not samePath:
        return False

    localExport = isExportLocal( node, jobProperties )
    if localExport:
        # When we override Frames and export is local, each render is done individually
        # If they have the same path (which we know they do at this point), they'll overwrite
        # When we don't override frames and the export is local, only a single render is done
        overrideFrames = jobProperties.get( "overrideframes", False )
        return overrideFrames
    else:
        # If it's rendered with Deadline (Which at this point we know it is) and it's not contiguous,
        # multiple tasks will be submitted that will overwrite if they write to the same filename
        frameList = GetFrameList( node, jobProperties )
        isContiguous = bool( re.match(r"^(-)?[0-9]*([-:](-)?[0-9]*)?$", frameList) )
        return not isContiguous

def GetFrameList( node, jobProperties ):
    """
    Parses a frame list either from the given render node or from the job properties, if an override is present
    :param node: The render node to be rendered
    :param jobProperties: The current job's properties, which may have an override value for the frame list
    :return: The framelist, parsed by Deadline Command so it can be submitted as part of a job
    """
    frameList = jobProperties.get( "framelist","0" ) if jobProperties.get( "overrideframes", False ) else GetFrameInfo( node )
    frameList = CallDeadlineCommand( [ "-ParseFrameList", frameList, "True" ] ).strip()
    return frameList

def GetFrameInfo( renderNode ):
    startFrame = 0
    endFrame = 0
    frameStep = 1
    frameString = ""

    if renderNode.type().description() == "Wedge":
        if renderNode.parm("driver").eval():
            return GetFrameInfo(renderNode.node(renderNode.parm("driver").eval()))

    #check if the nodes `Valid Frame Range` is set to 'Current Frame Only'
    if renderNode.parm('trange') and renderNode.parm('trange').evalAsString() == 'off':
        return str(int(hou.frame()))

    startFrameParm = renderNode.parm( "f1" )
    if startFrameParm != None:
        startFrame = int(startFrameParm.eval())

    endFrameParm = renderNode.parm( "f2" )
    if endFrameParm != None:
        endFrame = int(endFrameParm.eval())

    frameStepParm = renderNode.parm( "f3" )
    if frameStepParm != None:
        frameStep = int(frameStepParm.eval())

    frameString = str(startFrame) + "-" + str(endFrame)
    if frameStep > 1:
        frameString = frameString + "x" + str(frameStep)

    return frameString

def RightReplace( fullString, oldString, newString, occurences ):
    return newString.join( fullString.rsplit( oldString, occurences ) )

def ConcatenatePipelineToolSettingsToJob( jobInfoPath, batchName ):
    """
    Concatenate pipeline tool settings for the scene to the .job file.
    Arguments:
        jobInfoPath (str): Path to the .job file.
        batchName (str): Value of the 'batchName' job info entry, if it is required.
    """
    integrationDir = json.loads( hou.getenv( 'Deadline_Submission_Info' ) )[ 'RepoDirs' ][ 'submission/Integration/Main' ]
    jobWriterPath = os.path.join( integrationDir, 'JobWriter.py' )
    scenePath = hou.hipFile.path()
    argArray = ["-ExecuteScript", jobWriterPath, "Houdini", "--write", "--scene-path", scenePath, "--job-path", jobInfoPath, "--batch-name", batchName]
    CallDeadlineCommand(argArray)


def file_should_be_precached(file_parm, files_to_ignore=()):
    """
    It's not critical if something doesn't get pre-cached as the File Transfer system will just grab the file at render
    time. So we will bias towards not uploading something as to not waste transfers and balloon the Job object. If
    something does get added for pre-caching, but isn't in an Asset Transfer share, the Worker will not block on
    picking up a job. As such it is also not critical to be super through. The things that are cared about the most are
    avoid ballooning the job object unnecessarily and uploading extraneous files, ie. output files.
    The file should not be pre-cached if any of the following are true:
        The file parm is None.
        The file parm is a soho path.
        The file parm is disabled.
        The file parm path is part of the files to ignore.
        The file node value is derived from somewhere else.
    :param file_parm: The Houdini node parameter that contains the file to check for pre-caching eligibility.
                      http://www.sidefx.com/docs/houdini/hom/hou/Parm.html
    :param files_to_ignore: Default: (). Additional files that should be ignored for pre-caching.
    :return: Whether or not the file parm is eligible for pre-caching
    """
    # If the parm is None, then it's intrinsic to the scene and doesn't need to be uploaded. For example it could be a
    # Redshift ROP node, which should already be installed on the EC2 instance.
    if file_parm is None:
        return False

    # The soho program is the Python script that runs the render. This should be included with the renderer on the EC2
    # instance. As such we don't need to pre-cache it.
    if file_parm.name() == "soho_program":
        return False

    # Disabled nodes have no effect so we should be fine ignoring them.
    if file_parm.isDisabled():
        return False

    try:
        if file_parm.unexpandedString() in files_to_ignore:
            return False
    except hou.OperationFailed:
        # You can't unexpand parms with Keyframes in them, so we'll just ignore that here. There's not a lot of value to
        # pre-caching Keyframed assets as they should only be needed by one frame and adding them all to the Job object
        # could easily make it massive. Grabbing them at render time should be fine.
        pass

    file_node = file_parm.node()

    # If the node is inside a locked HDA and is not specifically marked as Editable then the value is derived
    # from somewhere else. For example, a point cloud that is generated at render time. In this case the file won't
    # exist at pre-cache time.
    if file_node.isInsideLockedHDA() and not file_node.isEditableInsideLockedHDA():
        return False

    return True


def get_asset_paths_to_precache(scene_file_is_aux, files_to_ignore=()):
    """
    Get the full paths of files to pre-cache. If the Houdini scene file isn't submitted with the job it will be added as
    an asset to pre-cache.
    :param scene_file_is_aux: Whether or not the Houdini scene file is an auxiliary file/submitted with the job.
    :param files_to_ignore: A set or tuple of files to be ignored for pre-caching
    :return: A list of asset paths to be pre-cached.
    """
    asset_paths_to_precache = []

    if not scene_file_is_aux:
        asset_paths_to_precache.append(hou.hipFile.path())

    for file_reference_parm, _ in hou.fileReferences():
        if file_should_be_precached(file_reference_parm, files_to_ignore=files_to_ignore):
            # Houdini will return the paths with tokens in them, ie. $HIP/somefile.png. We need to evaluate these tokens
            # as AWS Asset Transfer needs to know their precise location.
            evaluated_path = file_reference_parm.eval()

            # If the paths doesn't exist we won't pre-cache it. Filters out a lot of stuff and has the nice side effect
            # of not erroneously putting in things like other Houdini nodes.
            if os.path.exists(evaluated_path):
                asset_paths_to_precache.append(evaluated_path)

    return asset_paths_to_precache


def write_asset_paths_to_job_file(asset_paths, job_file):
    """
    NOTE: This should only called once per job file. Doing it more than that will result in duplicate entries in the
    job file.
    Write the asset paths of the files to pre-cache to the job file. Should be of the form
    AWSAssetFile<asset_number>=<asset_file_path>
    :param asset_paths: The assets paths to write to the job file.
    :param job_file: The file handle of the job file to write the asset paths to.
    """
    for index, asset_path in enumerate(asset_paths):
        job_file.write("AWSAssetFile{0}={1}\n".format(index, asset_path))


def get_render_output_filepath(node):
    """
    This function gets the output path for a given node,
    as the output object, it's path, or a padded filepath for Deadline

    :param node: The node which gets it's output checked
    :return output: The new output object
    :return outputFile: output file path
    :return paddedOutputFile: output file path, padded Deadline style
    """
    # Check the output file
    output = GetOutputPath( node )
    outputFile = ""
    paddedOutputFile = ""
    if output and output != "COMMAND":
        outputFile = output.eval()
        matches = PADDED_NUMBER_REGEX.findall( os.path.basename( outputFile ) )
        if matches != None and len( matches ) > 0:
            paddingString = matches[ len( matches ) - 1 ]
            paddingSize = len( paddingString )
            padding = "#" * paddingSize if paddingSize else "#"
            paddedOutputFile = RightReplace( outputFile, paddingString, padding, 1 )
    elif output is None and node.type().description() == "RenderMan":
        print( 'Warning: RenderMan 21 has deprecated the "RenderMan" node, please use the newer "RenderMan RIS" node.' )
    elif output != "COMMAND":
        print("Output path for ROP: \"%s\" is not specified" % node.path())
    else:
        print("Unable to resolve output path for ROP: \"%s\"" % node.path())
    
    if node.type().description() == "Octane":
        if node.parm("HO_img_fileFormat").eval() < 2 or node.parm("HO_img_fileFormat").eval() > 3:
            paddedOutputFile += ".exr"
        else:
            paddedOutputFile += ".png"
    
    return output, outputFile, paddedOutputFile


def get_standalone_export_path(node):
    """
    Provides the exported file's path as an export path and a padded filepath

    :param node: The node exported from
    :return exportFile: export file path
    :return paddedExportFile: exportFile, padded Deadline style
    """

    #get export file path for standalone job
    exportFileParameter = GetExportPath( node )
    exportFile = ""
    paddedExportFile = ""
    if exportFileParameter != None:
        exportFile = exportFileParameter.eval()
        matches = PADDED_NUMBER_REGEX.findall( os.path.basename( exportFile ) )
        if matches != None and len( matches ) > 0:
            paddingString = matches[ len( matches ) - 1 ]
            paddingSize = len( paddingString )
            padding = "0".zfill(paddingSize)
            paddedExportFile = RightReplace( exportFile, paddingString, padding, 1 )
        else:
            paddedExportFile = exportFile

    return exportFile, paddedExportFile

def get_renderman_standalone_export_path(node):
    """
    Provides the exported file's path for RenderMan.
    Uses a special Deadline's frame token instead of a frame number.

    :param node: The node exported from
    :return: export file path
    """
    export_file_parameter = GetExportPath( node )
    export_file = ''
    if export_file_parameter != None:
        original_unexpended = export_file_parameter.unexpandedString()
        unexpended = original_unexpended

        FRAME_TOKEN_REGEX = re.compile( '(\$F([0-9]*))' )
        matches = FRAME_TOKEN_REGEX.findall( unexpended )
        for match in matches:
            houdini_token = match[0]
            padding_size = ''
            if len(match) > 1 and match[1] != '':
                padding_size = match[1]

            deadline_token = '<_FRAME' + padding_size + '_>'
            unexpended = unexpended.replace(houdini_token, deadline_token)

        export_file_parameter.set(unexpended)
        export_file = export_file_parameter.eval()

        # Set the parameter value back to original value, so we don't modify the scene.
        export_file_parameter.set(original_unexpended)

    return export_file

def determine_chunk_size(node, jobProperties):
    """
    Given a node and job properties get the chunk size for the job.
    """

    #Arbitrarily large chunk size for use when we need all frames in 1 task.
    ALL_FRAMES_CHUNK_SIZE = 10000

    if node.type().description() == "HQueue Simulation":
        return 1

    if node.type().name() == "rop_alembic":
        if not node.parm("render_full_range").eval():
            return ALL_FRAMES_CHUNK_SIZE

    if is_vray_renderer_node( node ):
        # Check to see whether multiple .vrscene files will be written
        if not export_will_overwrite( node, jobProperties ) and single_export_file( node ):
            # Only one .vrscene file will be written, so there should only be one task
            return ALL_FRAMES_CHUNK_SIZE

    if node.type().nameWithCategory() == 'Driver/geometry' and node.parm('initsim') and node.parm('initsim').eval():
        # Initialize Simulation ops is enabled, which restarts the simulation when you attempt to render the node.
        return ALL_FRAMES_CHUNK_SIZE


    if jobProperties.get( "tilesenabled", False ) and jobProperties.get( "tilessingleframeenabled", False ) and \
        NodeSupportsTiles(node) and isExportJob( node, jobProperties ):
            return 1

    return jobProperties.get( "framespertask", 1 )


def SubmitRenderJob( node, jobProperties, dependencies ):
    jobCount = 1

    should_precache = jobProperties.get("shouldprecache", False)

    tilesEnabled = jobProperties.get( "tilesenabled", False )
    tilesInX = jobProperties.get( "tilesinx", 1 )
    tilesInY = jobProperties.get( "tilesiny", 1 )
    regionCount = tilesInX * tilesInY
    singleFrameTiles = jobProperties.get( "tilessingleframeenabled", False )
    singleFrame = jobProperties.get( "tilessingleframe", 1)

    jigsawEnabled = jobProperties.get( "jigsawenabled", False )
    jigsawRegionCount =  jobProperties.get( "jigsawregioncount", 1 )
    jigsawRegions = jobProperties.get( "jigsawregions", [] )

    if jigsawEnabled:
        regionCount = jigsawRegionCount

    if tilesEnabled:
        tilesEnabled = NodeSupportsTiles( node )

    regionJobCount = 1
    if tilesEnabled and not singleFrameTiles:
        regionJobCount = regionCount

    ignoreInputs = jobProperties.get( "ignoreinputs", True )

    separateWedgeJobs = jobProperties.get( "separateWedgeJobs", False )
    isWedge = node.type().description() == "Wedge"

    isHQueueSim = node.type().description() == "HQueue Simulation"
    isArnold = node.type().description() == "Arnold"
    isVray = is_vray_renderer_node( node )
    isRedshift = ( node.type().description() == "Redshift" )

    wedgeJobCount = 1
    if isWedge and separateWedgeJobs:
        wedgeJobCount = WedgeTasks( node )

    groupBatch = jobProperties.get( "batch", False )

    exportJob = isExportJob( node, jobProperties )
    localExport = isExportLocal( node, jobProperties )

    subInfo = json.loads( hou.getenv("Deadline_Submission_Info") )
    homeDir = subInfo["UserHomeDir"]

    renderJobIds = []
    exportJobIds = []
    assemblyJobIds = []

    if exportJob:
        exportType = node.type().description()

        # rename the export type to RenderMan so the RenderMan Deadline plugin is used
        if exportType == "RenderMan RIS":
            exportType = "RenderMan"

        if exportType == "RenderMan":
            ifdFile = get_renderman_standalone_export_path(node)
        else:
            #get ifdfile path for export
            ifdFile, paddedIfdFile = get_standalone_export_path(node)

        if ifdFile == "":
            exportJob = False

    #get the output file path
    output, outputFile, paddedOutputFile = get_render_output_filepath(node)

    # Get the IFD info, if applicable
    for wedgeNum in range(wedgeJobCount):
        if localExport:
            if singleFrameTiles and tilesEnabled:
                node.render( (singleFrame,singleFrame,1), (), ignore_inputs=ignoreInputs )
            else:
                exportPath = ""

                if isVray: # we need to temporarily change the export path to avoid overwriting, then change it back later
                    exportPath = node.parm("render_export_filepath").unexpandedString()
                    if export_will_overwrite( node, jobProperties ): # temporarily change to have frame numbers
                        node.parm("render_export_filepath").set(".$F4".join(os.path.splitext(exportPath)))

                frameStep = 1

                if jobProperties.get( "overrideframes", False ):
                    frameList = CallDeadlineCommand( [ "-ParseFrameList", jobProperties.get( "framelist", "0" ) , "False" ] ).strip()
                    renderFrames = frameList.split( "," )
                    for frame in renderFrames:
                        frame = int( frame )
                        node.render( ( frame, frame, frameStep ), (), ignore_inputs=ignoreInputs )
                else:
                    startFrame = 1
                    startFrameParm = node.parm( "f1" )
                    if startFrameParm != None:
                        startFrame = int(startFrameParm.eval())

                    endFrame = 1
                    endFrameParm = node.parm( "f2" )
                    if endFrameParm != None:
                        endFrame = int(endFrameParm.eval())

                    frameStepParm = node.parm( "f3" )
                    if frameStepParm != None:
                        frameStep = int(frameStepParm.eval())

                    # This seems to be here erroneously, and removes padding from Image viewing in Deadline
                    if output and output != "COMMAND" and not isVray:
                        paddedOutputFile = output.eval()

                    node.render( (startFrame,endFrame,frameStep), (), ignore_inputs=ignoreInputs )

                if isVray:
                    node.parm("render_export_filepath").set(exportPath) # Leave it how we found it
        else:
            for regionjobNum in range( 0, regionJobCount ):
                doShotgun = not ( exportJob or tilesEnabled )
                doDraft = not ( exportJob or tilesEnabled )

                jobName = jobProperties.get( "jobname", "Untitled" )
                jobName = "%s - %s"%(jobName, node.path())

                if isWedge and separateWedgeJobs:
                    jobName = jobName + "{WEDGE #"+str(wedgeNum)+"}"

                if tilesEnabled and singleFrameTiles and not exportJob:
                    jobName = jobName + " - Region "+str( regionjobNum )

                # Create submission info file
                jobInfoFile = os.path.join(homeDir, "temp", "houdini_submit_info%d.job") % ( wedgeNum * regionJobCount + regionjobNum )
                with open( jobInfoFile, "w" ) as fileHandle:
                    fileHandle.write( "Plugin=Houdini\n" )
                    fileHandle.write( "Name=%s\n" % jobName )
                    fileHandle.write( "Comment=%s\n" % jobProperties.get( "comment", "" ) )
                    fileHandle.write( "Department=%s\n" % jobProperties.get( "department", "" ) )
                    fileHandle.write( "Pool=%s\n" % jobProperties.get( "pool", "None" ) )
                    fileHandle.write( "SecondaryPool=%s\n" % jobProperties.get( "secondarypool", "" ) )
                    fileHandle.write( "Group=%s\n" % jobProperties.get( "group", "None" ) )
                    fileHandle.write( "Priority=%s\n" % jobProperties.get( "priority", 50 ) )
                    fileHandle.write( "TaskTimeoutMinutes=%s\n" % jobProperties.get( "tasktimeout", 0 ) )
                    fileHandle.write( "EnableAutoTimeout=%s\n" % jobProperties.get( "autotimeout", False ) )
                    fileHandle.write( "ConcurrentTasks=%s\n" % jobProperties.get( "concurrent", 1 ) )
                    fileHandle.write( "MachineLimit=%s\n" % jobProperties.get( "machinelimit", 0 ) )
                    fileHandle.write( "LimitConcurrentTasksToNumberOfCpus=%s\n" % jobProperties.get( "slavelimit", False ) )
                    fileHandle.write( "LimitGroups=%s\n" % jobProperties.get( "limits", 0 ) )
                    fileHandle.write( "JobDependencies=%s\n" % dependencies )
                    fileHandle.write( "OnJobComplete=%s\n" % jobProperties.get( "onjobcomplete", "Nothing" ) )

                    #When we render Wedge nodes with separateWedgeJobs disabled a single job is submitted where each task is a different wedge ID instead of the actual render frame
                    #When we render tile jobs with singleFrameTiles enabled each task is a separate tile for the same frame instead of the actual render frame.
                    #In both of these cases we do not want the Job to be Frame dependent since the frames will not match.
                    if not ( isWedge and not separateWedgeJobs ) and not ( tilesEnabled and singleFrameTiles ):
                        fileHandle.write( "IsFrameDependent=%s\n" % jobProperties.get( "isframedependent", "True" ) )

                    if jobProperties.get( "jobsuspended", False ):
                        fileHandle.write( "InitialStatus=Suspended\n" )

                    if jobProperties.get( "isblacklist", False ):
                        fileHandle.write( "Blacklist=%s\n" % jobProperties.get( "machinelist", "" ) )
                    else:
                        fileHandle.write( "Whitelist=%s\n" % jobProperties.get( "machinelist", "" ) )

                    if isHQueueSim:
                        sliceCount = hqueueSliceCount( node )
                        fileHandle.write( "Frames=0-%s\n" % ( sliceCount - 1 ) )
                    elif singleFrameTiles and tilesEnabled:
                        if not exportJob:
                            fileHandle.write( "TileJob=True\n" )
                            if jigsawEnabled:
                                fileHandle.write( "TileJobTilesInX=%s\n" % jigsawRegionCount )
                                fileHandle.write( "TileJobTilesInY=%s\n" % 1 )
                            else:
                                fileHandle.write( "TileJobTilesInX=%s\n" % tilesInX )
                                fileHandle.write( "TileJobTilesInY=%s\n" % tilesInY )
                            fileHandle.write( "TileJobFrame=%s\n" % singleFrame  )
                        else:
                            fileHandle.write( "Frames=%s\n" % singleFrame )
                    else:
                        fileHandle.write( "Frames=%s\n" % GetFrameList( node, jobProperties) )

                    fileHandle.write( "ChunkSize=%s\n" % determine_chunk_size(node, jobProperties) )

                    if tilesEnabled and singleFrameTiles and not exportJob:
                        imageFileName = outputFile
                        tileName = ""
                        paddingRegex = re.compile( "(#+)", re.IGNORECASE )
                        matches = PADDED_NUMBER_REGEX.findall( imageFileName )
                        if matches != None and len( matches ) > 0:
                            paddingString = matches[ len( matches ) - 1 ]
                            paddingSize = len( paddingString )
                            padding = str( singleFrame )
                            padding = "_tile?_" + padding
                            tileName = RightReplace( imageFileName, paddingString, padding, 1 )
                        else:
                            splitFilename = os.path.splitext(imageFileName)
                            tileName = splitFilename[0]+"_tile?_"+splitFilename[1]

                        tileRange = range(0, tilesInX*tilesInY)
                        if jigsawEnabled:
                            tileRange = range(0, jigsawRegionCount)

                        for currTile in tileRange:
                            regionOutputFileName = tileName.replace( "?", str(currTile) )
                            fileHandle.write( "OutputFilename0Tile%s=%s\n"%(currTile,regionOutputFileName) )

                    if not exportJob:
                        if paddedOutputFile != "":
                            tempPaddedOutputFile = paddedOutputFile
                            if isRedshift:
                                rsFormat = node.parm( "RS_outputFileFormat" ).evalAsString()
                                if not os.path.splitext( tempPaddedOutputFile )[1] == rsFormat:
                                    tempPaddedOutputFile += rsFormat

                            fileHandle.write( "OutputFilename0=%s\n" % tempPaddedOutputFile )
                            doDraft = True
                            doShotgun = True
                    elif ifdFile != "":
                        fileHandle.write( "OutputDirectory0=%s\n" % os.path.dirname( ifdFile ) )

                    if ( singleFrameTiles and tilesEnabled ) or exportJob or separateWedgeJobs:
                        groupBatch = True

                    if groupBatch:
                        fileHandle.write( "BatchName=%s\n" % jobProperties.get( "jobname", "Untitled" ) )

                    assets_to_precache = []
                    if should_precache:
                        assets_to_precache = get_asset_paths_to_precache(
                            scene_file_is_aux=jobProperties.get("submitscene", False),
                            files_to_ignore={output.unexpandedString()} if output and output != 'COMMAND' else {}
                        )
                        write_asset_paths_to_job_file(assets_to_precache, fileHandle)

                if not (tilesEnabled or exportJob):
                    ConcatenatePipelineToolSettingsToJob( jobInfoFile, jobProperties.get( "jobname", "Untitled" ) )

                pluginInfoFile = os.path.join( homeDir, "temp", "houdini_plugin_info%d.job" % (wedgeNum * regionJobCount + regionjobNum) )
                with open( pluginInfoFile, "w" ) as fileHandle:
                    if not jobProperties.get( "submitscene",False ):
                        fileHandle.write( "SceneFile=%s\n" % hou.hipFile.path() )

                    # This is only needed for output nodes that aren't using the HOUDINI_PATHMAP env variable and
                    # are not using houdini's tokens for the path. ie. $HIP.
                    try:
                        if output and output != "COMMAND":
                            fileHandle.write( "Output=%s\n" % output.unexpandedString() )
                            if isVray and export_will_overwrite( node, jobProperties ):
                                exportFile = ".$F4".join(os.path.splitext(ifdFile))
                                fileHandle.write( "IFD=%s\n" % exportFile )
                    except hou.OperationFailed:
                        # This error only occurs when KeyFrames are used in the output path.
                        print( "Unable to unexpand path with Key Frames. Skipping output." )

                    #alf sets it's own output driver
                    if node.type().description() == "Alfred" and node.parm( "alf_driver" ) != None:
                        fileHandle.write( "OutputDriver=%s\n" % node.parm( "alf_driver" ).eval() )
                    else:
                        fileHandle.write( "OutputDriver=%s\n" % node.path() )

                    fileHandle.write( "IgnoreInputs=%s\n" % jobProperties.get( "ignoreinputs", False ) )
                    ver = hou.applicationVersion()
                    fileHandle.write( "Version=%s.%s\n" % ( ver[0], ver[1] ) )
                    fileHandle.write( "Build=%s\n" % jobProperties.get( "bits", "None" ) )

                    if isHQueueSim:
                        fileHandle.write( "SimJob=True\n" )
                        sliceType = node.parm( "slice_type" ).evalAsString()
                        requiresTracking = ( sliceType == "volume" or sliceType == "particle" )
                        fileHandle.write( "SimRequiresTracking=%s\n" % requiresTracking )

                    if separateWedgeJobs and isWedge:
                        fileHandle.write("WedgeNum=%s\n" % wedgeNum )

                    fileHandle.write( "OpenCLUseGPU=%s\n" % jobProperties.get( "gpuopenclenable", False ) )
                    fileHandle.write( "GPUsPerTask=%s\n" % jobProperties.get( "gpuspertask", 0 ) )
                    fileHandle.write( "SelectGPUDevices=%s\n" % jobProperties.get( "gpudevices", "" ) )

                    if not exportJob and tilesEnabled:
                        fileHandle.write( "RegionRendering=True\n" )
                        if singleFrameTiles:
                            curRegion = 0
                            if jigsawEnabled:
                                for region in range( 0, jigsawRegionCount ):
                                    xstart = jigsawRegions[region*4]
                                    xend = jigsawRegions[region*4 + 1]
                                    ystart = jigsawRegions[region*4 + 2]
                                    yend = jigsawRegions[region*4 + 3]

                                    fileHandle.write( "RegionLeft%s=%s\n" % (curRegion, xstart) )
                                    fileHandle.write( "RegionRight%s=%s\n" % (curRegion, xend) )
                                    fileHandle.write( "RegionBottom%s=%s\n" % (curRegion, ystart) )
                                    fileHandle.write( "RegionTop%s=%s\n" % (curRegion,yend) )
                                    curRegion += 1
                            else:
                                for y in range(0, tilesInY):
                                    for x in range(0, tilesInX):

                                        xstart = x * 1.0 / tilesInX
                                        xend = ( x + 1.0 ) / tilesInX
                                        ystart = y * 1.0 / tilesInY
                                        yend = ( y + 1.0 ) / tilesInY

                                        fileHandle.write( "RegionLeft%s=%s\n" % (curRegion, xstart) )
                                        fileHandle.write( "RegionRight%s=%s\n" % (curRegion, xend) )
                                        fileHandle.write( "RegionBottom%s=%s\n" % (curRegion, ystart) )
                                        fileHandle.write( "RegionTop%s=%s\n" % (curRegion,yend) )
                                        curRegion += 1
                        else:
                            fileHandle.write( "CurrentTile=%s\n" % regionjobNum )

                            if jigsawEnabled:
                                xstart = jigsawRegions[ regionjobNum * 4 ]
                                xend = jigsawRegions[ regionjobNum * 4 + 1 ]
                                ystart = jigsawRegions[ regionjobNum * 4 + 2 ]
                                yend = jigsawRegions[ regionjobNum * 4 + 3 ]

                                fileHandle.write( "RegionLeft=%s\n" % xstart )
                                fileHandle.write( "RegionRight=%s\n" % xend )
                                fileHandle.write( "RegionBottom=%s\n" % ystart )
                                fileHandle.write( "RegionTop=%s\n" % yend )
                            else:
                                curY, curX = divmod(regionjobNum, tilesInX)

                                xstart = curX * 1.0 / tilesInX
                                xend = ( curX + 1.0 ) / tilesInX
                                ystart = curY * 1.0 / tilesInY
                                yend = ( curY + 1.0 ) / tilesInY

                                fileHandle.write( "RegionLeft=%s\n" % xstart )
                                fileHandle.write( "RegionRight=%s\n" % xend )
                                fileHandle.write( "RegionBottom=%s\n" % ystart )
                                fileHandle.write( "RegionTop=%s\n" % yend )

                arguments = [ jobInfoFile, pluginInfoFile ]
                if jobProperties.get( "submitscene", False ):
                    arguments.append( hou.hipFile.path() )

                jobResult = CallDeadlineCommand( arguments )
                jobId = GetJobIdFromSubmission( jobResult )
                renderJobIds.append( jobId )

                print("---------------------------------------------------")
                print( "\n".join( [ line.strip() for line in jobResult.split( "\n" ) if line.strip() ] ) )

                if should_precache and assets_to_precache:
                    precache_result = CallDeadlineCommand(['-AWSPortalPrecacheJob', jobId])
                    print(precache_result)

                print("---------------------------------------------------")

        if exportJob:
            exportTilesEnabled = tilesEnabled
            exportJobCount = 1

            if is_vray_renderer_node( node ):
                exportType = "Vray"

            lowerExportType = exportType.lower()
            if exportTilesEnabled:
                if ( exportType == "Mantra" and node.parm("vm_tile_render") is not None ) or exportType == "Arnold":
                    if not singleFrameTiles:
                        if jigsawEnabled:
                            exportJobCount = jigsawRegionCount
                        else:
                            exportJobCount = tilesInX * tilesInY
                else:
                    exportTilesEnabled = False
            exportJobDependencies = ",".join( renderJobIds )

            for exportJobNum in range( 0, exportJobCount ):
                exportJobInfoFile = os.path.join( homeDir, "temp", "export_job_info%d.job" % exportJobNum )
                exportPluginInfoFile = os.path.join( homeDir, "temp", "export_plugin_info%d.job" % exportJobNum )
                exportJobName = ( jobProperties.get( "jobname", "Untitled" ) + "- " + exportType + "- " +node.path() )
                if exportTilesEnabled and not singleFrameTiles:
                    exportJobName += " - Region " + str( exportJobNum )

                with open( exportJobInfoFile, 'w' ) as fileHandle:
                    fileHandle.write( "Plugin=%s\n" % exportType )
                    fileHandle.write( "Name=%s\n" % exportJobName )
                    if exportTilesEnabled or not isExportLocal( node, jobProperties ):
                        fileHandle.write( "BatchName=%s\n" % jobProperties.get( "jobname", "Untitled" ) )

                    fileHandle.write( "Comment=%s\n" % jobProperties.get( "comment", "" ) )
                    fileHandle.write( "Department=%s\n" % jobProperties.get( "department", "" ) )
                    fileHandle.write( "Pool=%s\n" % jobProperties.get( ( "%spool" % lowerExportType ), "None" ) )
                    fileHandle.write( "SecondaryPool=%s\n" % jobProperties.get( ( "%ssecondarypool" % lowerExportType ), "" ) )
                    fileHandle.write( "Group=%s\n" % jobProperties.get( ( "%sgroup" % lowerExportType ), "None" ) )
                    fileHandle.write( "Priority=%s\n" % jobProperties.get( ( "%spriority" % lowerExportType ), 50 ) )
                    fileHandle.write( "TaskTimeoutMinutes=%s\n" % jobProperties.get( ( "%stasktimeout" % lowerExportType ), 0 ) )
                    fileHandle.write( "EnableAutoTimeout=%s\n" % jobProperties.get( ( "%sautotimeout" % lowerExportType ), False ) )
                    fileHandle.write( "ConcurrentTasks=%s\n" % jobProperties.get( ( "%sconcurrent" % lowerExportType ), 1 ) )
                    fileHandle.write( "MachineLimit=%s\n" % jobProperties.get( ( "%smachinelimit" % lowerExportType ), 0 ) )
                    fileHandle.write( "LimitConcurrentTasksToNumberOfCpus=%s\n" % jobProperties.get( ( "%sslavelimit" % lowerExportType ), False ) )
                    fileHandle.write( "LimitGroups=%s\n" % jobProperties.get( ( "%slimits" % lowerExportType ), 0 ) )
                    fileHandle.write( "JobDependencies=%s\n" % exportJobDependencies )

                    if exportType == "Vray" and single_export_file( node ) and not export_will_overwrite( node, jobProperties ):
                        fileHandle.write( "IsFrameDependent=false\n" )
                    else:
                        fileHandle.write( "IsFrameDependent=true\n" )

                    fileHandle.write( "OnJobComplete=%s\n" % jobProperties.get( "%sonjobcomplete" % lowerExportType, jobProperties.get( "onjobcomplete", "Nothing" ) ) )

                    if jobProperties.get( "jobsuspended", False ):
                        fileHandle.write( "InitialStatus=Suspended\n" )

                    if jobProperties.get( ( "%sisblacklist" % lowerExportType ), False ):
                        fileHandle.write( "Blacklist=%s\n" % jobProperties.get( ( "%smachinelist" % lowerExportType ), "" ) )
                    else:
                        fileHandle.write( "Whitelist=%s\n" % jobProperties.get( ( "%smachinelist" % lowerExportType ), "" ) )

                    if exportTilesEnabled and singleFrameTiles:
                        fileHandle.write( "TileJob=True\n" )
                        if jigsawEnabled:
                            fileHandle.write( "TileJobTilesInX=%s\n" % jigsawRegionCount )
                            fileHandle.write( "TileJobTilesInY=%s\n" % 1 )
                        else:
                            fileHandle.write( "TileJobTilesInX=%s\n" % tilesInX )
                            fileHandle.write( "TileJobTilesInY=%s\n" % tilesInY )

                        fileHandle.write( "TileJobFrame=%s\n" % singleFrame )
                    elif jobProperties.get( "overrideframes", False ):
                        fileHandle.write( "Frames=%s\n" % jobProperties.get( "framelist","0" ) )
                        fileHandle.write( "ChunkSize=1\n" )
                    else:
                        fileHandle.write( "Frames=%s\n" % GetFrameInfo( node ) )
                        fileHandle.write( "ChunkSize=1\n" )

                    if paddedOutputFile != "":
                        if exportTilesEnabled and singleFrameTiles:
                            tileName = paddedOutputFile
                            paddingRegex = re.compile( "(#+)", re.IGNORECASE )
                            matches = paddingRegex.findall( os.path.basename( tileName ) )
                            if matches != None and len( matches ) > 0:
                                paddingString = matches[ len( matches ) - 1 ]
                                paddingSize = len( paddingString )
                                padding = str(singleFrame)
                                while len(padding) < paddingSize:
                                    padding = "0" + padding

                                padding = "_tile?_" + padding
                                tileName = RightReplace( tileName, paddingString, padding, 1 )
                            else:
                                splitFilename = os.path.splitext(tileName)
                                tileName = splitFilename[0]+"_tile?_"+splitFilename[1]

                            for currTile in range(0, tilesInX*tilesInY):
                                regionOutputFileName = tileName.replace( "?", str(currTile) )
                                fileHandle.write( "OutputFilename0Tile%s=%s\n"%(currTile,regionOutputFileName) )

                        else:
                            fileHandle.write( "OutputFilename0=%s\n" % paddedOutputFile)

                if not tilesEnabled:
                    ConcatenatePipelineToolSettingsToJob( exportJobInfoFile, jobProperties.get( "jobname", "Untitled" ) )

                with open( exportPluginInfoFile, 'w' ) as fileHandle:
                    if exportType == "Mantra":
                        fileHandle.write( "SceneFile=%s\n" % paddedIfdFile )

                        majorVersion, minorVersion = hou.applicationVersion()[:2]
                        fileHandle.write( "Version=%s.%s\n" % ( majorVersion, minorVersion ) )
                        fileHandle.write( "Threads=%s\n" % jobProperties.get( "mantrathreads", 0 ) )
                        fileHandle.write( "CommandLineOptions=\n" )

                        if exportTilesEnabled:
                            fileHandle.write( "RegionRendering=True\n" )
                            if singleFrameTiles:
                                curRegion = 0
                                if jigsawEnabled:
                                    for region in range(0,jigsawRegionCount):
                                        xstart = jigsawRegions[ region * 4 ]
                                        xend = jigsawRegions[ region * 4 + 1 ]
                                        ystart = jigsawRegions[ region * 4 + 2 ]
                                        yend = jigsawRegions[ region * 4 + 3 ]

                                        fileHandle.write( "RegionLeft%s=%s\n" % (curRegion, xstart) )
                                        fileHandle.write( "RegionRight%s=%s\n" % (curRegion, xend) )
                                        fileHandle.write( "RegionBottom%s=%s\n" % (curRegion, ystart) )
                                        fileHandle.write( "RegionTop%s=%s\n" % (curRegion,yend) )
                                        curRegion += 1
                                else:
                                    for y in range(0, tilesInY):
                                        for x in range(0, tilesInX):

                                            xstart = x * 1.0 / tilesInX
                                            xend = ( x + 1.0 ) / tilesInX
                                            ystart = y * 1.0 / tilesInY
                                            yend = ( y + 1.0 ) / tilesInY

                                            fileHandle.write( "RegionLeft%s=%s\n" % (curRegion, xstart) )
                                            fileHandle.write( "RegionRight%s=%s\n" % (curRegion, xend) )
                                            fileHandle.write( "RegionBottom%s=%s\n" % (curRegion, ystart) )
                                            fileHandle.write( "RegionTop%s=%s\n" % (curRegion,yend) )
                                            curRegion += 1
                            else:
                                fileHandle.write( "CurrentTile=%s\n" % exportJobNum )

                                if jigsawEnabled:

                                    xstart = jigsawRegions[exportJobNum*4]
                                    xend = jigsawRegions[exportJobNum*4+1]
                                    ystart = jigsawRegions[exportJobNum*4+2]
                                    yend = jigsawRegions[exportJobNum*4+3]

                                    fileHandle.write( "RegionLeft=%s\n" % xstart )
                                    fileHandle.write( "RegionRight=%s\n" % xend )
                                    fileHandle.write( "RegionBottom=%s\n" % ystart )
                                    fileHandle.write( "RegionTop=%s\n" % yend )
                                else:
                                    curY, curX = divmod(exportJobNum, tilesInX)

                                    xstart = curX * 1.0 / tilesInX
                                    xend = ( curX + 1.0 ) / tilesInX
                                    ystart = curY * 1.0 / tilesInY
                                    yend = ( curY + 1.0 ) / tilesInY

                                    fileHandle.write( "RegionLeft=%s\n" % xstart )
                                    fileHandle.write( "RegionRight=%s\n" % xend )
                                    fileHandle.write( "RegionBottom=%s\n" % ystart )
                                    fileHandle.write( "RegionTop=%s\n" % yend )

                    elif exportType == "Arnold":
                        fileHandle.write( "InputFile=" + ifdFile + "\n" )
                        fileHandle.write( "Threads=%s\n" % jobProperties.get( "arnoldthreads", 0 ) )
                        fileHandle.write( "CommandLineOptions=\n" )
                        fileHandle.write( "Verbose=4\n" )

                        if exportTilesEnabled:
                            fileHandle.write( "RegionJob=True\n" )

                            camera = node.parm( "camera" ).eval()
                            cameraNode = node.node(camera)

                            width = cameraNode.parm("resx").eval()
                            height = cameraNode.parm("resy").eval()

                            if singleFrameTiles:
                                fileHandle.write( "SingleAss=True\n" )
                                fileHandle.write( "SingleRegionFrame=%s\n"% singleFrame )
                                curRegion = 0


                                output = GetOutputPath( node )
                                imageFileName = outputFile
                                if imageFileName == "":
                                    continue

                                tileName = ""
                                outputName = ""
                                paddingRegex = re.compile( "(#+)", re.IGNORECASE )
                                matches = PADDED_NUMBER_REGEX.findall( imageFileName )
                                if matches != None and len( matches ) > 0:
                                    paddingString = matches[ len( matches ) - 1 ]
                                    paddingSize = len( paddingString )
                                    padding = str(singleFrame)
                                    while len(padding) < paddingSize:
                                        padding = "0" + padding

                                    outputName = RightReplace( imageFileName, paddingString, padding, 1 )
                                    padding = "_tile#_" + padding
                                    tileName = RightReplace( imageFileName, paddingString, padding, 1 )
                                else:
                                    outputName = imageFileName
                                    splitFilename = os.path.splitext(imageFileName)
                                    tileName = splitFilename[0]+"_tile#_"+splitFilename[1]

                                if jigsawEnabled:
                                    for region in range(0,jigsawRegionCount):
                                        xstart = int(jigsawRegions[region*4] * width +0.5 )
                                        xend = int(jigsawRegions[region*4+1] * width +0.5 )
                                        ystart = int(jigsawRegions[region*4+2] * height +0.5 )
                                        yend = int(jigsawRegions[region*4+3] * height +0.5 )

                                        if xend >= width:
                                            xend  = width-1
                                        if yend >= height:
                                            yend  = height-1

                                        regionOutputFileName = tileName
                                        matches = paddingRegex.findall( os.path.basename( tileName ) )
                                        if matches != None and len( matches ) > 0:
                                            paddingString = matches[ len( matches ) - 1 ]
                                            paddingSize = len( paddingString )
                                            padding = str(curRegion)
                                            while len(padding) < paddingSize:
                                                padding = "0" + padding
                                            regionOutputFileName = RightReplace( tileName, paddingString, padding, 1 )

                                        fileHandle.write( "RegionFilename%s=%s\n" % (curRegion, regionOutputFileName) )
                                        fileHandle.write( "RegionLeft%s=%s\n" % (curRegion, xstart) )
                                        fileHandle.write( "RegionRight%s=%s\n" % (curRegion, xend) )
                                        fileHandle.write( "RegionBottom%s=%s\n" % (curRegion,yend) )
                                        fileHandle.write( "RegionTop%s=%s\n" % (curRegion,ystart) )
                                        curRegion += 1
                                else:
                                    for y in range(0, tilesInY):
                                        for x in range(0, tilesInX):

                                            xstart = x * 1.0 / tilesInX
                                            xend = ( x + 1.0 ) / tilesInX
                                            ystart = y * 1.0 / tilesInY
                                            yend = ( y + 1.0 ) / tilesInY

                                            xstart = int(xstart * width +0.5 )
                                            xend = int(xend * width +0.5 )
                                            ystart = int(ystart * height +0.5 )
                                            yend = int(yend * height +0.5 )

                                            if xend >= width:
                                                xend  = width-1
                                            if yend >= height:
                                                yend  = height-1

                                            regionOutputFileName = tileName
                                            matches = paddingRegex.findall( os.path.basename( tileName ) )
                                            if matches != None and len( matches ) > 0:
                                                paddingString = matches[ len( matches ) - 1 ]
                                                paddingSize = len( paddingString )
                                                padding = str(curRegion)
                                                while len(padding) < paddingSize:
                                                    padding = "0" + padding
                                                regionOutputFileName = RightReplace( tileName, paddingString, padding, 1 )

                                            fileHandle.write( "RegionFilename%s=%s\n" % (curRegion, regionOutputFileName) )
                                            fileHandle.write( "RegionLeft%s=%s\n" % (curRegion, xstart) )
                                            fileHandle.write( "RegionRight%s=%s\n" % (curRegion, xend) )
                                            fileHandle.write( "RegionBottom%s=%s\n" % (curRegion, yend) )
                                            fileHandle.write( "RegionTop%s=%s\n" % (curRegion,ystart) )
                                            curRegion += 1
                            else:
                                fileHandle.write( "CurrentTile=%s\n" % exportJobNum )
                                fileHandle.write( "SingleAss=False\n" )
                                if jigsawEnabled:
                                    xstart = jigsawRegions[exportJobNum*4]
                                    xend = jigsawRegions[exportJobNum*4+1]
                                    ystart = jigsawRegions[exportJobNum*4+2]
                                    yend = jigsawRegions[exportJobNum*4+3]

                                    fileHandle.write( "RegionLeft=%s\n" % xstart )
                                    fileHandle.write( "RegionRight=%s\n" % xend )
                                    fileHandle.write( "RegionBottom=%s\n" % ystart )
                                    fileHandle.write( "RegionTop=%s\n" % yend )
                                else:
                                    curY = 0
                                    curX = 0
                                    jobNumberFound = False
                                    tempJobNum = 0
                                    for y in range(0, tilesInY):
                                        for x in range(0, tilesInX):
                                            if tempJobNum == exportJobNum:
                                                curY = y
                                                curX = x
                                                jobNumberFound = True
                                                break
                                            tempJobNum = tempJobNum + 1
                                        if jobNumberFound:
                                            break

                                    xstart = curX * 1.0 / tilesInX
                                    xend = ( curX + 1.0 ) / tilesInX
                                    ystart = curY * 1.0 / tilesInY
                                    yend = ( curY + 1.0 ) / tilesInY

                                    fileHandle.write( "RegionLeft=%s\n" % xstart )
                                    fileHandle.write( "RegionRight=%s\n" % xend )
                                    fileHandle.write( "RegionBottom=%s\n" % ystart )
                                    fileHandle.write( "RegionTop=%s\n" % yend )

                    elif exportType == "RenderMan":
                        fileHandle.write( "RibFile=" + ifdFile + "\n" )
                        fileHandle.write( "FramePadding=above22\n" )
                        fileHandle.write( "Threads=%s\n" % jobProperties.get( "rendermanthreads", 0 ) )
                        fileHandle.write( "CommandLineOptions=%s\n" % jobProperties.get( "rendermanarguments", "" ) )
                        fileHandle.write( "WorkingDirectory=\n" )

                    elif exportType == "Redshift":
                        fileHandle.write( "SceneFile=%s\n" % ifdFile )
                        fileHandle.write( "WorkingDirectory=\n" )
                        fileHandle.write( "CommandLineOptions=%s\n" % jobProperties.get( "redshiftarguments", "" ) )
                        fileHandle.write( "GPUsPerTask=%s\n" % jobProperties.get( "gpuspertask", 0 ) )
                        fileHandle.write( "SelectGPUDevices=%s\n" % jobProperties.get( "gpudevices", "" ) )
                        fileHandle.write( "ImageOutputDirectory=%s\n" % os.path.dirname( outputFile ) )

                    elif exportType == "Vray":
                        exportFileName = ifdFile
                        if export_will_overwrite( node, jobProperties ):
                            exportFileName = hou.expandString(".$F4").join(os.path.splitext(ifdFile))
                        fileHandle.write( "InputFilename=%s\n" % exportFileName )
                        fileHandle.write( "CommandLineOptions=%s\n" % jobProperties.get( "vrayarguments", "" ) )
                        fileHandle.write( "Threads=%s\n" % jobProperties.get( "vraythreads", 0 ) )

                        # Check whether the .vrscene file names are different
                        SeparateFilesPerFrame = ( not single_export_file( node ) ) or export_will_overwrite( node, jobProperties )
                        fileHandle.write( "SeparateFilesPerFrame=%s\n" % SeparateFilesPerFrame )

                arguments = [ exportJobInfoFile, exportPluginInfoFile ]

                jobResult = CallDeadlineCommand( arguments )
                jobId = GetJobIdFromSubmission( jobResult )
                exportJobIds.append( jobId )

                print("---------------------------------------------------")
                print( "\n".join( [ line.strip() for line in jobResult.split( "\n" ) if line.strip() ] ) )
                print("---------------------------------------------------")

        if tilesEnabled and jobProperties.get( "submitdependentassembly" ) and ( renderJobIds or exportJobIds ):
            assemblyJobIds = []

            renderFrames = None
            if singleFrameTiles:
                renderFrames = [ singleFrame ]
            else:
                if jobProperties.get( "overrideframes", False ):
                    frameList = CallDeadlineCommand( [ "-ParseFrameList", jobProperties.get( "framelist","0" ) ,"False" ] ).strip()
                    renderFrames = frameList.split( "," )
                else:
                    frameList = CallDeadlineCommand( [ "-ParseFrameList", GetFrameInfo( node ), "False" ] ).strip()
                    renderFrames = frameList.split( "," )

            jobName = jobProperties.get( "jobname", "Untitled" )
            jobName = "%s - %s - Assembly"%(jobName, node.path())

            # Create submission info file
            jobInfoFile = os.path.join(homeDir, "temp", "jigsaw_submit_info%d.job") % wedgeNum
            with open( jobInfoFile, "w" ) as fileHandle:
                fileHandle.write( "Plugin=DraftTileAssembler\n" )
                fileHandle.write( "Name=%s\n" % jobName )
                fileHandle.write( "Comment=%s\n" % jobProperties.get( "comment", "" ) )
                fileHandle.write( "Department=%s\n" % jobProperties.get( "department", "" ) )
                fileHandle.write( "Pool=%s\n" % jobProperties.get( "pool", "None" ) )
                fileHandle.write( "SecondaryPool=%s\n" % jobProperties.get( "secondarypool", "" ) )
                fileHandle.write( "Group=%s\n" % jobProperties.get( "group", "None" ) )
                fileHandle.write( "Priority=%s\n" % jobProperties.get( "priority", 50 ) )
                fileHandle.write( "TaskTimeoutMinutes=%s\n" % jobProperties.get( "tasktimeout", 0 ) )
                fileHandle.write( "EnableAutoTimeout=%s\n" % jobProperties.get( "autotimeout", False ) )
                fileHandle.write( "ConcurrentTasks=%s\n" % jobProperties.get( "concurrent", 1 ) )
                fileHandle.write( "MachineLimit=%s\n" % jobProperties.get( "machinelimit", 0 ) )
                fileHandle.write( "LimitConcurrentTasksToNumberOfCpus=%s\n" % jobProperties.get( "slavelimit", False ) )
                fileHandle.write( "LimitGroups=%s\n" % jobProperties.get( "limits", 0 ) )
                if exportJob:
                    fileHandle.write( "JobDependencies=%s\n" % ",".join( exportJobIds ) )
                else:
                    fileHandle.write( "JobDependencies=%s\n" % ",".join( renderJobIds ) )
                fileHandle.write( "OnJobComplete=%s\n" % jobProperties.get( "onjobcomplete", "Nothing" ) )

                if jobProperties.get( "jobsuspended", False ):
                    fileHandle.write( "InitialStatus=Suspended\n" )

                if jobProperties.get( "isblacklist", False ):
                    fileHandle.write( "Blacklist=%s\n" % jobProperties.get( "machinelist", "" ) )
                else:
                    fileHandle.write( "Whitelist=%s\n" % jobProperties.get( "machinelist", "" ) )


                if singleFrameTiles:
                    fileHandle.write( "Frames=%s\n" % singleFrame )
                else:
                    fileHandle.write( "IsFrameDependent=true\n" )
                    if jobProperties.get( "overrideframes", False ):
                        fileHandle.write( "Frames=%s\n" % jobProperties.get( "framelist","0" ) )
                    else:
                        fileHandle.write( "Frames=%s\n" % GetFrameInfo( node ) )

                fileHandle.write( "ChunkSize=1\n" )

                if paddedOutputFile != "":
                    fileHandle.write( "OutputFilename0=%s\n" % paddedOutputFile )
                else:
                    fileHandle.write( "OutputDirectory0=%s\n" % os.path.dirname( ifdFile ) )

                fileHandle.write( "BatchName=%s\n" % jobProperties.get( "jobname", "Untitled" ) )

            ConcatenatePipelineToolSettingsToJob( jobInfoFile, jobProperties.get( "jobname", "Untitled" ) )
            # Create plugin info file
            pluginInfoFile = os.path.join( homeDir, "temp", "jigsaw_plugin_info%d.job" % wedgeNum )
            with open( pluginInfoFile, "w" ) as fileHandle:

                fileHandle.write( "ErrorOnMissing=%s\n" % jobProperties.get( "erroronmissingtiles", True ) )
                fileHandle.write( "ErrorOnMissingBackground=%s\n" % jobProperties.get( "erroronmissingbackground", True ) )

                fileHandle.write( "CleanupTiles=%s\n" % jobProperties.get( "cleanuptiles", True ) )
                fileHandle.write( "MultipleConfigFiles=%s\n" % True )

            configFiles = []

            for frame in renderFrames:

                output = GetOutputPath( node )
                imageFileName = outputFile

                tileName = ""
                outputName = ""
                paddingRegex = re.compile( "(#+)", re.IGNORECASE )
                matches = PADDED_NUMBER_REGEX.findall( imageFileName )
                if matches != None and len( matches ) > 0:
                    paddingString = matches[ len( matches ) - 1 ]
                    paddingSize = len( paddingString )
                    padding = str(frame)
                    while len(padding) < paddingSize:
                        padding = "0" + padding

                    outputName = RightReplace( imageFileName, paddingString, padding, 1 )
                    padding = "_tile#_" + padding
                    tileName = RightReplace( imageFileName, paddingString, padding, 1 )
                else:
                    outputName = imageFileName
                    splitFilename = os.path.splitext(imageFileName)
                    tileName = splitFilename[0]+"_tile#_"+splitFilename[1]

                # Create the directory for the config file if it doesn't exist.
                directory = os.path.dirname(imageFileName)
                if not os.path.exists(directory):
                    os.makedirs(directory)

                fileName, fileExtension = os.path.splitext(imageFileName)

                date = time.strftime("%Y_%m_%d_%H_%M_%S")
                configFilename = fileName+"_"+str(frame)+"_config_"+date+".txt"
                with open( configFilename, "w" ) as fileHandle:
                    fileHandle.write( "\n" )

                    fileHandle.write( "ImageFileName=" +outputName +"\n" )
                    backgroundType = jobProperties.get( "backgroundoption", "None" )

                    if backgroundType == "Previous Output":
                        fileHandle.write( "BackgroundSource=" +outputName +"\n" )
                    elif backgroundType == "Selected Image":
                        fileHandle.write( "BackgroundSource=" + jobProperties.get( "backgroundimage", "" ) +"\n" )

                    if isArnold:
                        renderWidth = cameraNode.parm("resx").eval()
                        renderHeight = cameraNode.parm("resy").eval()
                        fileHandle.write("ImageHeight=%s\n" % renderHeight)
                        fileHandle.write("ImageWidth=%s\n" % renderWidth)
                    fileHandle.write( "TilesCropped=False\n" )

                    if jigsawEnabled:
                        fileHandle.write( "TileCount=" +str( jigsawRegionCount ) + "\n" )
                    else:
                        fileHandle.write( "TileCount=" +str( tilesInX * tilesInY ) + "\n" )
                    fileHandle.write( "DistanceAsPixels=False\n" )

                    currTile = 0
                    if jigsawEnabled:
                        for region in range(0,jigsawRegionCount):
                            width = jigsawRegions[region*4+1]-jigsawRegions[region*4]
                            height = jigsawRegions[region*4+3]-jigsawRegions[region*4+2]
                            xRegion = jigsawRegions[region*4]
                            yRegion = jigsawRegions[region*4+2]

                            regionOutputFileName = tileName
                            matches = paddingRegex.findall( os.path.basename( tileName ) )
                            if matches != None and len( matches ) > 0:
                                paddingString = matches[ len( matches ) - 1 ]
                                paddingSize = len( paddingString )
                                padding = str(currTile)
                                while len(padding) < paddingSize:
                                    padding = "0" + padding
                                regionOutputFileName = RightReplace( tileName, paddingString, padding, 1 )

                            fileHandle.write( "Tile%iFileName=%s\n"%(currTile,regionOutputFileName) )
                            fileHandle.write( "Tile%iX=%s\n"%(currTile,xRegion) )
                            if isArnold:
                                fileHandle.write( "Tile%iY=%s\n"%(currTile,1.0-yRegion-height) )
                            else:
                                fileHandle.write( "Tile%iY=%s\n"%(currTile,yRegion) )
                            fileHandle.write( "Tile%iWidth=%s\n"%(currTile,width) )
                            fileHandle.write( "Tile%iHeight=%s\n"%(currTile,height) )
                            currTile += 1

                    else:
                        for y in range(0, tilesInY):
                            for x in range(0, tilesInX):
                                width = 1.0/tilesInX
                                height = 1.0/tilesInY
                                xRegion = x*width
                                yRegion = y*height

                                regionOutputFileName = tileName
                                matches = paddingRegex.findall( os.path.basename( tileName ) )
                                if matches != None and len( matches ) > 0:
                                    paddingString = matches[ len( matches ) - 1 ]
                                    paddingSize = len( paddingString )
                                    padding = str(currTile)
                                    while len(padding) < paddingSize:
                                        padding = "0" + padding
                                    regionOutputFileName = RightReplace( tileName, paddingString, padding, 1 )

                                fileHandle.write( "Tile%iFileName=%s\n"%(currTile,regionOutputFileName) )
                                fileHandle.write( "Tile%iX=%s\n"%(currTile,xRegion) )
                                if isArnold:
                                    fileHandle.write( "Tile%iY=%s\n"%(currTile,1.0-yRegion-height) )
                                else:
                                    fileHandle.write( "Tile%iY=%s\n"%(currTile,yRegion) )
                                fileHandle.write( "Tile%iWidth=%s\n"%(currTile,width) )
                                fileHandle.write( "Tile%iHeight=%s\n"%(currTile,height) )
                                currTile += 1

                    configFiles.append(configFilename)

            arguments = [ jobInfoFile, pluginInfoFile ]
            arguments.extend( configFiles )

            jobResult = CallDeadlineCommand( arguments )
            jobId = GetJobIdFromSubmission( jobResult )
            assemblyJobIds.append( jobId )

            print("---------------------------------------------------")
            print("\n".join( [ line.strip() for line in jobResult.split("\n") if line.strip() ] ) )
            print("---------------------------------------------------")


    if not exportJob and not tilesEnabled:
        return renderJobIds
    elif exportJob and not tilesEnabled:
        return exportJobIds
    else:
        return assemblyJobIds
