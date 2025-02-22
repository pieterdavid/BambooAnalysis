"""
HTCondor tools (based on cp3-llbb/CommonTools condorSubmitter)
"""
__all__ = ("CommandListJob", "jobsFromTasks", "makeTasksMonitor", "findOutputsForCommands")

from itertools import chain, count
import logging
logger = logging.getLogger(__name__)
import os, os.path
import subprocess

from .batch import CommandListJob as CommandListJobBase

def makeExecutable(path):
    """ Set file permissions to executable """
    import stat
    if os.path.exists(path) and os.path.isfile(path):
        perm = os.stat(path)
        os.chmod(path, perm.st_mode | stat.S_IEXEC)

CondorJobStatus = [
          "Unexpanded"      # 0
        , "Idle"            # 1
        , "Running"         # 2
        , "Removed"         # 3
        , "Completed"       # 4
        , "Held"            # 5
        , "Submission_err"  # 6
        ]

class CommandListJob(CommandListJobBase):
    """
    Helper class to create a condor master job from a list of commands (each becoming one subjob)
    
    Default work directory will be $(pwd)/condor_work, default output pattern is "*.root"
    """
    def __init__(self, commandList, workDir=None, cmdLines=None, envSetupLines=None, outputPatterns=None):
        self.envSetupLines = envSetupLines if envSetupLines is not None else []
        self.outputPatterns = outputPatterns if outputPatterns is not None else ["*.root"]

        super(CommandListJob, self).__init__(commandList, workDir=workDir, workdir_default_pattern="condor_work")

        self.cmdLines = cmdLines
        self.masterCmd = self._writeCondorFiles()
        self.clusterId = None ## will be set by submit
 
    MasterCmd = (
        "should_transfer_files   = YES\n"
        "when_to_transfer_output = ON_EXIT\n"
        "arguments      = $(Process)\n"
        "executable     = {indir}/condor.sh\n"
        "output         = {logdir_rel}/condor_$(Process).out\n"
        "error          = {logdir_rel}/condor_$(Process).err\n"
        "log            = {logdir_rel}/condor_$(Process).log\n"
        "queue {nJobs:d}\n"
        )
    MasterShell = (
        "#!/usr/bin/env bash\n"
        "\n"
        ". {indir}/condor_$1.sh\n"
        )
    
    JobShell = (
        "#!/usr/bin/env bash\n"
        "\n"
        "{environment_setup}"
        "\n"
        "function move_files {{\n"
        "{move_fragment}"
        "\n}}\n"
        "\n"
        "{command} && move_files"
        )

    def _writeCondorFiles(self):
        """ Create Condor .sh and .cmd files """
        masterCmdName = os.path.join(self.workDirs["in"], "condor.cmd")
        with open(masterCmdName, "w") as masterCmd:
            if self.cmdLines:
                masterCmd.write("{0}\n".format("\n".join(self.cmdLines)))
            masterCmd.write(CommandListJob.MasterCmd.format(
                  indir=self.workDirs["in"]
                , logdir_rel=os.path.relpath(self.workDirs["log"])
                , nJobs=len(self.commandList)
                ))
        masterShName = os.path.join(self.workDirs["in"], "condor.sh")
        with open(masterShName, "w") as masterSh:
            masterSh.write(CommandListJob.MasterShell.format(
                  indir=self.workDirs["in"]
                ))
        makeExecutable(masterShName)

        for i,command in enumerate(self.commandList):
            jobShName = os.path.join(self.workDirs["in"], "condor_{:d}.sh".format(i))
            job_outdir = os.path.join(self.workDirs["out"], str(i))
            os.makedirs(job_outdir)
            with open(jobShName, "w") as jobSh:
                jobSh.write(CommandListJob.JobShell.format(
                      environment_setup="\n".join(self.envSetupLines)
                    , move_fragment="\n".join((
                        " for file in {pattern}; do\n"
                        '   echo "Moving $file to {outdir}/"\n'
                        "   mv $file {outdir}/\n"
                        " done"
                        ).format(pattern=ipatt, outdir=job_outdir)
                        for ipatt in self.outputPatterns)
                    , command=command
                    ))
            makeExecutable(jobShName)

        return masterCmdName

    def _commandOutDir(self, command):
        """ Output directory for a given command """
        return os.path.join(self.workDirs["out"], str(self.commandList.index(command)))
    def commandOutFiles(self, command):
        """ Output files for a given command """
        import fnmatch
        cmdOutDir = self._commandOutDir(command)
        return list( os.path.join(cmdOutDir, fn) for fn in os.listdir(cmdOutDir)
                if any( fnmatch.fnmatch(fn, pat) for pat in self.outputPatterns) )

    def submit(self):
        """ Submit the jobs to condor """
        logger.info("Submitting {0:d} condor jobs.".format(len(self.commandList)))
        result = subprocess.check_output(["condor_submit", self.masterCmd]).decode()

        import re
        pat = re.compile("\d+ job\(s\) submitted to cluster (\d+)\.")
        g = pat.search(result)
        self.clusterId = g.group(1)

        ## save to file in case
        with open(os.path.join(self.workDirs["in"], "cluster_id"), "w") as f:
            f.write(self.clusterId)

        logger.info("Submitted, job ID is {}".format(self.clusterId))

    def statuses(self):
        """ list of subjob statuses (numeric, using indices in CondorJobStatus) """
        if self.clusterId is None:
            raise Exception("Cannot get status before submitting the jobs to condor")
        return map(int, list(subprocess.check_output(["condor_q"      , self.clusterId, "-format", '%d ', "JobStatus"]).decode().strip().split())
                      + list(subprocess.check_output(["condor_history", self.clusterId, "-format", '%d ', "JobStatus"]).decode().strip().split()) )

    @property
    def status(self):
        statuses = self.statuses()
        if all(st == statuses[0] for st in statuses):
            return CondorJobStatus[statuses[0]]
        elif any(st == 2 for st in statuses):
            return "Running"
        elif any(st == 3 for st in statuses):
            return "Removed"
        else:
            return "unknown"

    def subjobStatus(self, i):
        subjobId = "{0}.{1:d}".format(self.clusterId, i)
        ret = subprocess.check_output(["condor_q", subjobId, "-format", '%d', "JobStatus"]).decode()
        if len(ret) == 0: # search in the completed ones
            ret = subprocess.check_output(["condor_history", subjobId, "-format", '%d', "JobStatus"]).decode()
        return CondorJobStatus[int(ret)]
    def commandStatus(self, command):
        return self.subjobStatus(self.commandList.index(command))

def jobsFromTasks(taskList, workdir=None, batchConfig=None, configOpts=None):
    cmdLines = []
    envSetupLines = []
    if configOpts:
        cmdLines += configOpts.get("cmd", [])
        envSetupLines += configOpts.get("env", [])
    if batchConfig:
        if "requirements" in batchConfig:
            cmdLines.append("requirements = {}".format(batchConfig["requirements"]))
    condorJob = CommandListJob(list(chain.from_iterable(task.commandList for task in taskList)),
            workDir=workdir, cmdLines=cmdLines, envSetupLines=envSetupLines)
    for task in taskList:
        task.jobCluster = condorJob
    return [ condorJob ]

def makeTasksMonitor(jobs=[], tasks=[], interval=120):
    """ make a TasksMonitor for condor jobs """
    from .batch import TasksMonitor
    return TasksMonitor(jobs=jobs, tasks=tasks, interval=interval
            , allStatuses=CondorJobStatus
            , activeStatuses=(1,2)
            , completedStatus=4
            )

def findOutputsForCommands(batchDir, commandMatchers):
    """
    Look for outputs of matching commands inside batch submission directory

    :param batchDir: batch submission directory (with an ``input/condor.cmd`` file)
    :param commandMatchers: a dictionary with matcher objects (return ``True`` when passed matching commands)

    :returns: tuple of a matches dictionary (same keys as commandMatchers, a list of output files from matching commands) and a list of IDs for subjobs without output
    """
    with open(os.path.join(batchDir, "input", "condor.cmd")) as cmdFile:
        nJobs = int(next(ln for ln in cmdFile if ln.startswith("queue ")).split()[1])
    cmds = []
    for iJ in range(nJobs):
        with open(os.path.join(batchDir, "input", "condor_{0:d}.sh".format(iJ))) as jobShFile:
            cmdLine = next(ln for ln in jobShFile if ln.strip().endswith(" && move_files"))
            cmds.append(cmdLine.split(" && ")[0])
    matches = dict()
    id_noOut = []
    for mName, matcher in commandMatchers.items():
        ids_matched = [ (i, cmd) for i, cmd in zip(count(), cmds) if matcher(cmd) ]
        files_found = []
        if not ids_matched:
            logger.warning(f"No jobs matched for {mName}")
        else:
            for sjId, cmd in ids_matched:
                outdir = os.path.join(batchDir, "output", str(sjId))
                if not os.path.exists(outdir):
                    logger.debug(f"Output directory for {mName} not found: {outdir} (command: {cmd})")
                    id_noOut.append(sjId)
                else:
                    sjOut = [ os.path.join(outdir, fn) for fn in os.listdir(outdir) ]
                    if not sjOut:
                        logger.debug(f"No output files for {mName} found in {outdir} (command: {cmd})")
                        id_noOut.append(sjId)
                    files_found += sjOut
        matches[mName] = len(ids_matched), files_found
    return matches, sorted(id_noOut)
