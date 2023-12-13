import sys
import os
import json
import traceback
import hou
import SubmitHoudiniToDeadlineFunctions
from CallDeadlineCommand import CallDeadlineCommand


def create_job_dict(render_node):

    framelist = str(int(render_node.evalParm("f1"))) + "-" + str(int(render_node.evalParm("f2")))
    jobname = hou.getenv("HIPNAME")
    pool = "houdini"
    secondarypool = "houdini"


    jobProperties = {
    'batch': False,
    'jobname': jobname,
    'pool': pool,
    'secondarypool': secondarypool,
    'group': 'none',
    'priority': 99,
    'tasktimeout': 0,
    'autotimeout': 0,
    'concurrent': 1,
    'machinelimit': 0,
    'slavelimit': 1,
    'limits': '',
    'onjobcomplete': 'Nothing',
    'jobsuspended': 0,
    'shouldprecache': 1,
    'isblacklist': 0,
    'machinelist': '',
    'overrideframes': 1,
    'framelist': framelist,
    'framespertask': 9999,
    'bits': '64bit',
    'submitscene': 0,
    'isframedependent': 0,
    'gpuopenclenable': 0,
    'gpuspertask': 0,
    'gpudevices': '',
    'ignoreinputs': 0,
    'separateWedgeJobs': 0,
    'mantrajob': 0,
    'mantrapool': 'none',
    'mantrasecondarypool': '',
    'mantragroup': 'none',
    'mantrapriority': 50,
    'mantratasktimeout': 0,
    'mantraautotimeout': 0,
    'mantraconcurrent': 1,
    'mantramachinelimit': 0,
    'mantraslavelimit': 1,
    'mantralimits': '',
    'mantraonjobcomplete': 'Nothing',
    'mantraisblacklist': 0,
    'mantramachinelist': '',
    'mantrathreads': 0,
    'mantralocalexport': False,
    'arnoldjob': 1,
    'arnoldpool': 'arnold',
    'arnoldsecondarypool': 'arnold',
    'arnoldgroup': 'none',
    'arnoldpriority': 50,
    'arnoldtasktimeout': 0,
    'arnoldautotimeout': 0,
    'arnoldconcurrent': 1,
    'arnoldmachinelimit': 0,
    'arnoldslavelimit': 1,
    'arnoldonjobcomplete': 'Nothing',
    'arnoldlimits': '',
    'arnoldisblacklist': 0,
    'arnoldmachinelist': '',
    'arnoldthreads': 0,
    'arnoldlocalexport': False,
    'rendermanjob': 0,
    'rendermanpool': 'none',
    'rendermansecondarypool': '',
    'rendermangroup': 'none',
    'rendermanpriority': 50,
    'rendermantasktimeout': 0,
    'rendermanconcurrent': 1,
    'rendermanmachinelimit': 0,
    'rendermanlimits': '',
    'rendermanonjobcomplete': 'Nothing',
    'rendermanisblacklist': 0,
    'rendermanmachinelist': '',
    'rendermanthreads': 0,
    'rendermanarguments': '',
    'rendermanlocalexport': False,
    'redshiftjob': 1,
    'redshiftpool': '',
    'redshiftsecondarypool': '',
    'redshiftgroup': 'none',
    'redshiftpriority': 50,
    'redshifttasktimeout': 0,
    'redshiftautotimeout': 0,
    'redshiftconcurrent': 1,
    'redshiftmachinelimit': 0,
    'redshiftslavelimit': 1,
    'redshiftlimits': '',
    'redshiftonjobcomplete': 'Nothing',
    'redshiftisblacklist': 0,
    'redshiftmachinelist': '', 
    'redshiftarguments': '', 
    'redshiftlocalexport': False,
    'vrayjob': 0, 
    'vraypool': 'none',
    'vraysecondarypool': '', 
    'vraygroup': 'none',
    'vraypriority': 50, 
    'vraytasktimeout': 0, 
    'vrayautotimeout': 0, 
    'vrayconcurrent': 1, 
    'vraymachinelimit': 0,
    'vrayslavelimit': 1,
    'vraylimits': '', 
    'vrayonjobcomplete': 'Nothing', 
    'vrayisblacklist': 0,
    'vraymachinelist': '', 
    'vraythreads': 0, 
    'vrayarguments': '', 
    'vraylocalexport': False, 
    'tilesenabled': 0,
    'tilesinx': 3, 
    'tilesiny': 3,
    'tilessingleframeenabled': 1, 
    'tilessingleframe': 1,
    'jigsawenabled': 1,
    'jigsawregioncount': 0,
    'jigsawregions': [],
    'submitdependentassembly': 1,
    'backgroundoption': 'Blank Image',
    'backgroundimage': '',
    'erroronmissingtiles': '1', 
    'erroronmissingbackground': '0',
    'cleanuptiles': '1'
    }
    return jobProperties


def run_job_cmd(render_node):

    SubmitHoudiniToDeadlineFunctions.SaveScene()

    jobProperties = create_job_dict(render_node)

    ## submit to Deadline ##
    flag = 0

    ## imports and sys paths for deadline ##
    try:
        from CallDeadlineCommand import CallDeadlineCommand
    except ImportError:
        path = ""
        print( "Please try copying the CallDeadlineCommand.py to the users/Documents/houdini<version>/python<v>libs.\n" )
        hou.ui.displayMessage( "I cannot find the CallDeadlineCommand.py Please try copying the CallDeadlineCommand.py to the users/Documents/houdini<version>/python<v>libs.", title="Submit Houdini To Deadline" )
    else:
        path = CallDeadlineCommand([ "-GetRepositoryPath", "submission/Houdini/Main" ]).strip()

    if path:
        path = path.replace( "\\", "/" )
        
        # Add the path to the system path
        if path not in sys.path:
            print("Appending \"" + path + "\" to system path to import SubmitHoudiniToDeadline module")
            sys.path.append( path )
        else:
            pass

        # Import the script and call the main() function
        try:
            import SubmitHoudiniToDeadline
        except:
            print( traceback.format_exc() )
            print( "The SubmitHoudiniToDeadline.py script could not be found in the Deadline Repository. Please make sure that the Deadline Client has been installed on this machine, that the Deadline Client bin folder is set in the DEADLINE_PATH environment variable, and that the Deadline Client has been configured to point to a valid Repository." )
    else:
        print( "The SubmitHoudiniToDeadline.py script could not be found in the Deadline Repository. Please make sure that the Deadline Client has been installed on this machine, that the Deadline Client bin folder is set in the DEADLINE_PATH environment variable, and that the Deadline Client has been configured to point to a valid Repository." )

    ## get deadline info ##
    print( "Grabbing submitter info..." )
    try:
        output = json.loads( CallDeadlineCommand( [ "-prettyJSON", "-GetSubmissionInfo", "Pools", "Groups", "MaxPriority", "TaskLimit", "UserHomeDir", "RepoDir:submission/Houdini/Main", "RepoDir:submission/Integration/Main", "RepoDirNoCustom:draft", "RepoDirNoCustom:submission/Jigsaw", ] ) )
    except:
        print( "Unable to get submitter info from Deadline:\n\n" + traceback.format_exc() )
        raise

    if output[ "ok" ]:
        submissionInfo = output[ "result" ]
        hou.putenv("Deadline_Submission_Info", json.dumps( submissionInfo ) )
    else:
        print( "DeadlineCommand disagrees and could not grab submitter info.\n\n" + output[ "result" ] )
        raise Exception( output[ "result" ] )

    ## submit render job ##
    try:
        import SubmitHoudiniToDeadlineFunctions as SHTDFunctions
        flag = 1
    except Exception as e:
        print(e)
        hou.ui.displayMessage("Library import failure. Deadline installation seems off.")

    if flag:
        try:
            jobIds = SHTDFunctions.SubmitRenderJob( render_node, jobProperties, "")
        except Exception as e:
            print(e)
            hou.ui.displayMessage("Can`t submit to Deadline Repo.")
    return output
