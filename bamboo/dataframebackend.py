"""
ROOT::RDataFrame backend classes
"""
import bamboo.logging
logger = bamboo.logging.getLogger(__name__)

from itertools import chain
from functools import partial
import numpy as np

from .plots import FactoryBackend, Selection, Plot, DerivedPlot
from . import treefunctions as op
from . import treeoperations as top

from collections import defaultdict
_RDFNodeStats = defaultdict(int)
_RDFHistoNDStats = defaultdict(int)
_RDFHistoND_methods = dict()

class SelWithDefines(top.CppStrRedir):
    def __init__(self, parent, variation="nominal"):
        self.explDefine = list()
        self.var = None ## nodes for related systematic variations (if different by more than the weight)
        if isinstance(parent, SelWithDefines):
            self.parent = parent
            self.backend = parent.backend
            self.df = parent.df
            self._definedColumns = dict(parent._definedColumns)
            if variation == "nominal":
                self.var = dict((varNm, SelWithDefines(pvar, variation=varNm)) for varNm, pvar in parent.var.items())
                ## parent is either nominal (when branching off), or the corresponding variation of the parent of the nominal node
        elif isinstance(parent, DataframeBackend):
            self.parent = None
            self.backend = parent
            self.df = parent.rootDF
            self._definedColumns = dict()
            self.var = dict()
        else:
            raise RuntimeError("Can only define SelWithDefines with a DataframeBackend or another SelWithDefines")
        self.wName = dict()
        top.CppStrRedir.__init__(self)

    def addWeight(self, weights=None, wName=None, parentWeight=None, variation="nominal"):
        if variation == "nominal" and parentWeight is None and self.parent and self.parent.wName:
            parentWeight = self.parent.wName["nominal"]
        if weights:
            weightExpr = Selection._makeExprProduct(
                ([top.adaptArg(op.extVar("float", parentWeight), typeHint="float")]+weights) if parentWeight
                else weights
                )
            self._define(wName, weightExpr)
            self.wName[variation] = wName
        elif parentWeight:
            self.wName[variation] = parentWeight
        else:
            assert not wName
            self.wName[variation] = None

    def addCut(self, cuts):
        cutExpr = Selection._makeExprAnd(cuts)
        cutStr = cutExpr.get_cppStr(defCache=self)
        self._addFilterStr(cutStr)

    def _addFilterStr(self, filterStr):
        logger.debug("Filtering with {0}", filterStr)
        self.df = self.df.Filter(filterStr)
        _RDFNodeStats["Filter"] += 1

    def _getColName(self, op):
        if op in self._definedColumns:
            return self._definedColumns[op]

    def define(self, expr):
        """ explicitly define column for expression (returns the column name) """
        if not self._getColName(expr):
            self.explDefine.append(expr)
        return self(expr)

    def _define(self, name, expr):
        if expr in self._definedColumns:
            cppStr = self(expr)
        else:
            cppStr = expr.get_cppStr(defCache=self)
        logger.debug("Defining {0} as {1}", name, cppStr)
        self.df = self.df.Define(name, cppStr)
        _RDFNodeStats["Define"] += 1
        self._definedColumns[expr] = name

    def symbol(self, decl, **kwargs):
        return self.backend.symbol(decl, **kwargs)

    def _inExplDefines(self, arg):
        return arg in self.explDefine or ( self.parent and self.parent._inExplDefines(arg) )

    def shouldDefine(self, arg):
        return self.backend.shouldDefine(arg, defCache=self) or self._inExplDefines(arg)

    def __call__(self, arg):
        """ Get the C++ string corresponding to an op """
        nm = self._getColName(arg)
        if ( not self.shouldDefine(arg) ) and not nm: ## the easy case
            try:
                return arg.get_cppStr(defCache=self)
            except Exception as ex:
                logger.error("Could not get cpp string for {0!r}: {1!r}", arg, ex)
                return "NONE"
        else:
            if not nm: ## define it then
                nm = self.backend.getUColName()
                self._define(nm, arg)
            return nm

## NOTE these are global (for the current process&interpreter)
## otherwise they would be overwritten in sequential mode (this even allows reuse)
_gSymbols = dict()
_giFun = 0

class DataframeBackend(FactoryBackend):
    def __init__(self, tree, outFileName=None):
        from .root import gbl
        self.rootDF = gbl.ROOT.RDataFrame(tree).Define("_zero_for_stats", "0")
        self.outFile = gbl.TFile.Open(outFileName, "CREATE") if outFileName else None
        self.selDFs = dict()      ## (selection name, variation) -> SelWithDefines
        self.results = dict()     ## product name -> list of result pointers
        self.allSysts = dict()    ## all systematic uncertainties and variations impacting any plot
        self._cfrMemo = defaultdict(dict)
        super(DataframeBackend, self).__init__()
        self._iCol = 0
    def _getUSymbName(self):
        global _giFun
        _giFun += 1
        return "myFun{0:d}".format(_giFun)
    def getUColName(self):
        self._iCol += 1
        return "myCol{0:d}".format(self._iCol)

    def shouldDefine(self, op, defCache=None):
        return any(isinstance(op, expType) for expType in (top.Select, top.Sort, top.Map, top.Next, top.Reduce, top.Combine, top.DefineOnFirstUse)) and op.canDefine
    def define(self, op, selection):
        self.selDFs[selection.name].define(op)

    def symbol(self, decl, resultType=None, args=None, nameHint=None):
        if resultType and args: ## then it needs to be wrapped in a function
            decl = "{result} <<name>>({args})\n{{\n  return {0};\n}};\n".format(
                        decl, result=resultType, args=args)
        global _gSymbols
        if decl in _gSymbols:
            return _gSymbols[decl]
        else:
            if nameHint and nameHint not in _gSymbols.values():
                name = nameHint
            else:
                name = self._getUSymbName()
            _gSymbols[decl] = name
            fullDecl = decl.replace("<<name>>", name)

            logger.debug("Defining new symbol with interpreter: {0}", fullDecl)
            from .root import gbl
            gbl.gInterpreter.Declare(fullDecl)
            _RDFNodeStats["gInterpreter_Declare"] += 1
            return name
    @staticmethod
    def create(decoTree, outFileName=None):
        inst = DataframeBackend(decoTree._tree, outFileName=None)
        rootSel = Selection(inst, "none")
        return inst, rootSel

    def addSelection(self, sele):
        """ Define ROOT::RDataFrame objects needed for this selection """
        if sele.name in self.selDFs:
            raise RuntimeError(f"A Selection with name '{sele.name}' already exists")
        cutStr = None
        nomParentNd = self.selDFs[sele.parent.name] if sele.parent else None
        if sele._cuts:
            assert sele.parent ## there *needs* to be a root no-op sel, so this is an assertion
            ## trick: by passing defCache=parentDF and doing this *before* constructing the nominal node,
            ## any definitions end up in the node above, and are in principle available for other sub-selections too
            cutStr = Selection._makeExprAnd(sele._cuts).get_cppStr(defCache=self.selDFs[sele.parent.name])
        nomNd = SelWithDefines(nomParentNd if nomParentNd else self)
        if cutStr:
            nomNd._addFilterStr(cutStr)
        nomNd.addWeight(weights=sele._weights, wName=("w_{0}".format(sele.name) if sele._weights else None))
        self.selDFs[sele.name] = nomNd

        if sele.autoSyst:
            weightSyst = sele.weightSystematics
            cutSyst = sele.cutSystematics
            for systN, systVars in sele.systematics.items(): ## the two above merged
                logger.debug("Adding weight variations {0} for systematic {1}", systVars, systN)
                ## figure out which cuts and weight factors are affected by this systematic
                isthissyst = partial((lambda sN,iw : isinstance(iw, top.OpWithSyst) and iw.systName == sN), systN)
                ctToChange = []
                ctKeep = list(sele._cuts)
                wfToChange = []
                wfKeep = list(sele._weights)
                if systN in cutSyst:
                    nRem = 0
                    for i,ct in enumerate(sele._cuts):
                        if any(top.collectNodes(ct, select=isthissyst)):
                            ctToChange.append(ct)
                            del ctKeep[i-nRem]
                            nRem += 1
                if systN in weightSyst:
                    nRem = 0
                    for i,wf in enumerate(sele._weights):
                        if any(top.collectNodes(wf, select=isthissyst)):
                            wfToChange.append(wf)
                            del wfKeep[i-nRem]
                            nRem += 1
                ## construct variation nodes (if necessary)
                for varn in systVars:
                    _hasthissystV = partial((lambda sV, iNd : isinstance(iNd, top.OpWithSyst) and sV in iNd.variations), varn)
                    hasthissystV = lambda nd : ( isthissyst(nd) and _hasthissystV(nd) )
                    ## add cuts to the appropriate node, if affected by systematics (here or up)
                    varParentNd = None ## set parent node if not the nominal one
                    if nomParentNd and varn in nomParentNd.var: ## -> continue on branch
                        varParentNd = nomParentNd.var[varn]
                    elif ctToChange: ## -> branch off now
                        varParentNd = nomParentNd
                    if not varParentNd: ## cuts unaffected (here and in parent), can stick with nominal
                        varNd = nomNd
                    else: ## on branch, so add cuts (if any)
                        if len(sele._cuts) == 0: ## no cuts, reuse parent
                            varNd = varParentNd
                        else:
                            ctChanged = []
                            for ct in ctToChange: ## empty if sele._cuts are not affected
                                newct = ct.clone(select=hasthissystV)
                                for nd in top.collectNodes(newct, select=hasthissystV):
                                    nd.changeVariation(varn)
                                ctChanged.append(newct)
                            cutStr = Selection._makeExprAnd(ctKeep+ctChanged).get_cppStr(defCache=varParentNd)
                            varNd = SelWithDefines(varParentNd)
                            varNd._addFilterStr(cutStr)
                        nomNd.var[varn] = varNd
                    ## next: attach weights (modified if needed) to varNd
                    if varParentNd:
                        parwn = varParentNd.wName.get(varn, varParentNd.wName.get("nominal"))
                    elif nomParentNd:
                        parwn = nomParentNd.wName.get(varn, nomParentNd.wName.get("nominal"))
                    else:
                        parwn = None ## no prior weights at all
                    if not sele._weights:
                        logger.debug("{0} systematic variation {1}: reusing {2}", sele.name, varn, parwn)
                        varNd.addWeight(parentWeight=parwn, variation=varn)
                    else:
                        if wfToChange or varNd != nomNd or ( nomParentNd and varn in nomParentNd.wName ):
                            wfChanged = []
                            for wf in wfToChange:
                                newf = wf.clone(select=hasthissystV)
                                for nd in top.collectNodes(newf, select=hasthissystV):
                                    nd.changeVariation(varn)
                                wfChanged.append(newf)
                            logger.debug("{0} systematic variation {1}: defining new weight based on {2}", sele.name, varn, parwn)
                            varNd.addWeight(weights=(wfKeep+wfChanged), wName=("w_{0}__{1}".format(sele.name, varn) if sele._weights else None), parentWeight=parwn, variation=varn)
                        else: ## varNd == nomNd, not branched, and parent does not have weight variation
                            logger.debug("{0} systematic variation {1}: reusing nominal {2}", sele.name, varn, varNd.wName["nominal"])
                            varNd.addWeight(parentWeight=varNd.wName["nominal"], variation=varn)

    def addPlot(self, plot, autoSyst=True):
        """ Define ROOT::RDataFrame objects needed for this plot (and keep track of the result pointer) """
        if plot.key in self.results:
            raise ValueError(f"A Plot with key '{plot.key}' has already been added")

        nomNd = self.selDFs[plot.selection.name]
        plotRes = []
        ## Add nominal plot
        nomVarNames = DataframeBackend.defineAndGetVarNames(nomNd, plot.variables, uName=plot.name)
        plotRes.append(DataframeBackend.makeHistoND(nomNd, DataframeBackend.makePlotModel(plot),
            nomVarNames, weightName=nomNd.wName["nominal"], plotName=plot.name))

        if plot.selection.autoSyst and autoSyst:
            ## Same for all the systematics
            varSysts = top.collectSystVars(plot.variables)
            selSysts = plot.selection.systematics
            allSysts = top.mergeSystVars(dict(plot.selection.systematics), varSysts)
            top.mergeSystVars(self.allSysts, allSysts)
            for systN, systVars in allSysts.items():
                isthissyst = partial((lambda sN,iw : isinstance(iw, top.OpWithSyst) and iw.systName == sN), systN)
                idxVarsToChange = []
                for i,xvar in enumerate(plot.variables):
                    if any(top.collectNodes(xvar, select=isthissyst)):
                        idxVarsToChange.append(i)
                for varn in systVars:
                    _hasthissystV = partial((lambda sV, iNd : isinstance(iNd, top.OpWithSyst) and sV in iNd.variations), varn)
                    hasthissystV = lambda nd : ( isthissyst(nd) and _hasthissystV(nd) )
                    if systN in varSysts or varn in nomNd.var:
                        varNd = nomNd.var.get(varn, nomNd)
                        varVars = []
                        for i,xvar in enumerate(plot.variables):
                            if i in idxVarsToChange:
                                varVar = xvar.clone(select=hasthissystV)
                                for nd in top.collectNodes(varVar, select=hasthissystV):
                                    nd.changeVariation(varn)
                            else:
                                varVar = xvar
                            varVars.append(varVar)
                        varNames = DataframeBackend.defineAndGetVarNames(varNd, varVars, uName=f"{plot.name}__{varn}")
                        wN = varNd.wName[varn] if systN in selSysts and varn in varNd.wName else varNd.wName["nominal"] ## else should be "only in the variables", so varNd == nomNd then
                        plotRes.append(DataframeBackend.makeHistoND(varNd,
                            DataframeBackend.makePlotModel(plot, variation=varn),
                            varNames, weightName=wN,
                            plotName=f"{plot.name} variation {varn}"))
                    else: ## can reuse variables, but may need to take care of weight
                        wN = nomNd.wName[varn]
                        plotRes.append(DataframeBackend.makeHistoND(nomNd,
                            DataframeBackend.makePlotModel(plot, variation=varn),
                            nomVarNames, weightName=wN,
                            plotName=f"{plot.name} variation {varn}"))
                        if not wN: ## no weight
                            raise RuntimeError("Systematic {0} (variation {1}) affects cuts, variables, nor weight of plot {2}... this should not happen".format(systN, varn, plot.name))

        self.results[plot.key] = plotRes

    @staticmethod
    def makePlotModel(plot, variation="nominal"):
        from .root import gbl
        binnings = plot.binnings
        modCls = getattr(gbl.ROOT.RDF, "TH{0:d}DModel".format(len(binnings)))
        name = plot.name
        if variation != "nominal":
            name = "__".join((name, variation))
        if len(binnings) > 1: # high-dimensional histo models require either all or none of the binnings to be uniform
            from .plots import EquidistantBinning, VariableBinning
            if any((isinstance(b, VariableBinning) for b in binnings)):
                import numpy as np
                binnings = [VariableBinning(np.linspace(b.minimum, b.maximum, b.N + 1)) if isinstance(b, EquidistantBinning) else b for b in binnings]
        return modCls(name, plot.title, *chain.from_iterable(
            DataframeBackend.makeBinArgs(binning) for binning in binnings))
    @staticmethod
    def makeBinArgs(binning):
        from .plots import EquidistantBinning, VariableBinning
        if isinstance(binning, EquidistantBinning):
            return (binning.N, binning.mn, binning.mx)
        elif isinstance(binning, VariableBinning):
            return (binning.N, np.array(binning.binEdges, dtype=np.float64))
        else:
            raise ValueError("Binning of unsupported type: {0!r}".format(binning))

    @staticmethod
    def defineAndGetVarNames(nd, variables, uName=None):
        varNames = []
        for i,var in enumerate(variables):
            if isinstance(var, top.GetColumn):
                varNames.append(var.name)
            elif isinstance(var, top.ForwardingOp) and isinstance(var.wrapped, top.GetColumn):
                varNames.append(var.wrapped.name)
            elif nd._getColName(var):
                varNames.append(nd._getColName(var))
            else:
                nm = f"v{i:d}_{uName}"
                nd._define(nm, var)
                varNames.append(nm)
        return varNames

    @staticmethod
    def makeHistoND(nd, plotModel, axVars, weightName=None, plotName=None):
        nVars = len(axVars)
        axTypes = [ nd.df.GetColumnType(cNm) for cNm in axVars ]
        useExplicit = True
        from .root import gbl
        for axTp in axTypes:
            try:
                tp = getattr(gbl, axTp)
                if hasattr(tp, "value_type"):
                    useExplicit = False
            except AttributeError:
                pass
        if weightName: ## nontrivial weight
            allVars = axVars + [ weightName ]
            logger.debug("Adding plot {0} with variables {1} and weight {2}", plotName, ", ".join(axVars), weightName)
        else:
            allVars = axVars
            logger.debug("Adding plot {0} with variables {1}", plotName, ", ".join(axVars))
        if useExplicit and nVars < 3: ## only have templates for those
            ndCppName = nd.df.__class__.__cpp_name__
            if weightName:
                wType = nd.df.GetColumnType(weightName)
                templTypes = [ndCppName] + axTypes + [ wType ]
                kyTypes = (ndCppName, tuple(axTypes), wType)
            else:
                templTypes = [ndCppName] + axTypes
                kyTypes = (ndCppName, tuple(axTypes))
            _RDFHistoNDStats[kyTypes] += 1
            if kyTypes not in _RDFHistoND_methods:
                logger.debug(f"Declaring Histo{nVars:d}D helper for types {templTypes}")
                _RDFHistoND_methods[kyTypes] = getattr(gbl.rdfhelpers.rdfhistofactory, f"Histo{nVars:d}D")[tuple(templTypes)]
            plotFun = partial(_RDFHistoND_methods[kyTypes], nd.df)
        else:
            logger.debug(f"Using Histo{nVars:d}D with type inference")
            plotFun = getattr(nd.df, f"Histo{nVars:d}D")
        _RDFNodeStats[f"Histo{nVars:d}D"] += 1
        return plotFun(plotModel, *allVars)

    def getResults(self, plot, key=None):
        return plot.produceResults(self.results.get(key if key is not None else plot.key), self)

    def writeSkim(self, sele, outputFile, treeName, definedBranches=None, origBranchesToKeep=None, maxSelected=-1):
        selND = self.selDFs[sele.name]

        allcolN = selND.df.GetColumnNames()
        defcolN = selND.df.GetDefinedColumnNames()
        colNToKeep = type(allcolN)()
        if origBranchesToKeep is None: ## keep all if not defined
            for cn in allcolN:
                if cn not in defcolN:
                    colNToKeep.push_back(cn)
        elif len(origBranchesToKeep) != 0:
            for cn in origBranchesToKeep:
                if cn not in allcolN:
                    raise RuntimeError("Requested column '{0}' from input not found".format(cn))
                if cn in defcolN:
                    raise RuntimeError("Requested column '{0}' from input is a defined column".format(cn))
                colNToKeep.push_back(cn)

        for dN, dExpr in definedBranches.items():
            if dN not in allcolN:
                selND._define(dN, top.adaptArg(dExpr))
            elif dN not in defcolN:
                logger.warning(f"Requested to add column {dN} with expression, but a column with the same name on the input tree exists. The latter will be copied instead")
            colNToKeep.push_back(dN)

        selDF = selND.df
        if maxSelected > 0:
            selDF = selDF.Range(maxSelected)

        selDF.Snapshot(treeName, outputFile, colNToKeep)
        from .root import gbl
        outF = gbl.TFile.Open(outputFile, "READ")
        nPass = outF.Get(treeName).GetEntries()
        outF.Close()
        if nPass == 0:
            logger.warning(f"No events selected, removing tree '{treeName}' to avoid problems with merging")
            outF = gbl.TFile.Open(outputFile, "UPDATE")
            ky = next(ky for ky in outF.GetListOfKeys() if ky.GetName() == treeName)
            ky.Delete()
            outF.Close()

    def addCutFlowReport(self, report, selections=None, autoSyst=True):
        if selections is None:
            selections = report.selections
        logger.debug("Adding cutflow report {0} for selection(s) {1}".format(report.name, ", ".join(sele.name for sele in selections)))
        cmArgs = {"autoSyst" : autoSyst, "makeEntry" : report.__class__.Entry, "prefix" : report.name}
        memo = self._cfrMemo[report.name]
        results = []
        for sele in selections:
            if sele.name in memo:
                cfr = memo[sele.name]
            else:
                cfr = self._makeCutFlowReport(sele, **cmArgs)
                memo[sele.name] = cfr
            results.append(cfr)
            if report.recursive:
                isel = sele.parent
                while isel is not None:
                    if isel.name in memo:
                        cfr_n = memo[isel.name]
                        cfr.setParent(cfr_n)
                        break ## all above should be there too, then
                    logger.debug("Adding cutflow report {0} for selection {1}".format(report.name, isel.name))
                    cfr_n = self._makeCutFlowReport(isel, **cmArgs)
                    memo[isel.name] = cfr_n
                    cfr.setParent(cfr_n)
                    cfr = cfr_n
                    isel = isel.parent
        self.results[report.name] = self.results.get(report.name, []) + results

    def _makeCutFlowReport(self, selection, autoSyst=True, makeEntry=None, prefix=None):
        from .root import gbl
        selND = self.selDFs[selection.name]
        nomWName = selND.wName["nominal"]
        nomName = f"{prefix}_{selection.name}"
        mod = gbl.ROOT.RDF.TH1DModel(nomName, f"CutFlowReport {prefix} nominal counter for {selection.name}", 1, 0., 1.)
        cfrNom = DataframeBackend.makeHistoND(selND, mod, ["_zero_for_stats"], weightName=nomWName, plotName=nomName)
        cfrSys = {}
        if autoSyst:
            for varNm in selection.systematics:
                if varNm in selND.var or selND.wName[varNm] != nomWName:
                    name = f"{prefix}_{selection.name}__{varNm}"
                    mod = gbl.ROOT.RDF.TH1DModel(name, f"CutFlowReport {prefix} {varNm} counter for {selection.name}", 1, 0., 1.)
                    cfrSys[varNm] = DataframeBackend.makeHistoND(selND.var.get(varNm, selND), mod,
                            ["_zero_for_stats"], weightName=selND.wName[varNm], plotName=title)
        return makeEntry(selection.name, cfrNom, cfrSys)

class LazyDataframeBackend(DataframeBackend):
    """
    An experiment: a FactoryBackend implementation that instantiates nodes late

    For testing, there is an extra method to instantiate what's needed for a bunch of plots
    """
    def __init__(self, tree, outFileName=None):
        super(LazyDataframeBackend, self).__init__(tree, outFileName=outFileName)
        self.selections = dict()
        self.definesPerSelection = dict()
        self.plotsPerSelection = dict()
        self.cutFlowReports = []
        self._definedSel = set()
    @staticmethod
    def create(decoTree, outFileName=None):
        inst = LazyDataframeBackend(decoTree._tree, outFileName=outFileName)
        rootSel = Selection(inst, "none")
        return inst, rootSel
    def addSelection(self, selection):
        ## keep track and do nothing
        if selection.name in self.selections:
            raise RuntimeError(f"A Selection with name '{selection.name}' already exists")
        self.selections[selection.name] = selection
        self.definesPerSelection[selection.name] = []
        self.plotsPerSelection[selection.name] = []
    def addPlot(self, plot, autoSyst=True):
        ## keep track and do nothing
        if any((ap.key == plot.key) for selPlots in self.plotsPerSelection.values() for (ap, aSyst) in selPlots):
            raise RuntimeError(f"A Plot with key '{plot.key}' already exists")
        self.plotsPerSelection[plot.selection.name].append((plot, autoSyst))
    def addCutFlowReport(self, report, selections=None, autoSyst=True):
        self.cutFlowReports.append((report, selections, autoSyst))
    def _buildSelGraph(self, selName, plotList):
        sele = self.selections[selName]
        if sele.parent and sele.parent.name not in self._definedSel:
            self._buildSelGraph(sele.parent.name, plotList)
        super(LazyDataframeBackend, self).addSelection(sele)
        for op in self.definesPerSelection[selName]:
            super(LazyDataframeBackend, self).define(op, sele)
        for plot, autoSyst in self.plotsPerSelection[selName]:
            if plot in plotList:
                super(LazyDataframeBackend, self).addPlot(plot, autoSyst=autoSyst)
        self._definedSel.add(selName)
    def buildGraph(self, plotList):
        ## this is the extra method: do all the addSelection/addPlot/addDerivedPlot calls in a better order
        ## collect all plots
        def getDeps_r(plot):
            if isinstance(plot, DerivedPlot):
                for dp in plot.dependencies:
                    yield dp
                    yield from getDeps_r(dp)
        allPlots = list(plotList) + list(chain.from_iterable(getDeps_r(p) for p in plotList))
        for plot in allPlots:
            if isinstance(plot, Plot):
                if plot.selection.name not in self._definedSel:
                    self._buildSelGraph(plot.selection.name, allPlots)
        for report, selections, autoSyst in self.cutFlowReports:
            super(LazyDataframeBackend, self).addCutFlowReport(report, selections=selections, autoSyst=autoSyst)
    def define(self, op, selection):
        self.definesPerSelection[selection.name].append(op)
    def writeSkim(self, sele, outputFile, treeName, definedBranches=None, origBranchesToKeep=None, maxSelected=-1):
        self._buildSelGraph(sele.name, [])
        super(LazyDataframeBackend, self).writeSkim(sele, outputFile, treeName, definedBranches=definedBranches, origBranchesToKeep=origBranchesToKeep, maxSelected=maxSelected)
