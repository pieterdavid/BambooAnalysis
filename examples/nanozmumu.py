"""
Example analysis module: make a dimuon mass plot from a NanoAOD
"""
from bamboo.analysismodules import NanoAODHistoModule, NanoAODSkimmerModule
import os.path
from bamboo.logging import getLogger
logger = getLogger(__name__)

class NanoZMuMu(NanoAODHistoModule):
    """ Example module: Z->MuMu histograms from NanoAOD """
    def prepareTree(self, tree, sample=None, sampleCfg=None):
        era = sampleCfg.get("era") if sampleCfg else None
        isMC = self.isMC(sample)
        metName = "METFixEE2017" if era == "2017" else "MET"
        isNotWorker = True # for tests - more realistic: (self.args.distributed != "worker")
        ## Decorate the tree
        from bamboo.treedecorators import NanoAODDescription, nanoRochesterCalc, nanoJetMETCalc
        tree,noSel,be,lumiArgs = super(NanoAODHistoModule, self).prepareTree(tree, sample=sample, sampleCfg=sampleCfg,
                description=NanoAODDescription.get("v5", year=(era if era else "2016"), isMC=isMC,
                    systVariations=[ nanoRochesterCalc, (nanoJetMETCalc_METFixEE2017 if era == "2017" else nanoJetMETCalc) ])) ## will do Jet and MET variations, and the Rochester correction
        ## per-year/era options
        puWeightsFile = None
        jecTag, smearTag, jesUncertaintySources = None, None, None
        rochesterFile = None
        if era == "2016":
            rochesterFile = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests", "data", "RoccoR2016.txt")
            if isMC:
                puWeightsFile = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests", "data", "puweights.json")
                jecTag = "Summer16_07Aug2017_V20_MC"
                smearTag = "Summer16_25nsV1_MC"
                jesUncertaintySources = ["Total"]
            else:
                if "2016B" in sample or "2016C" in sample or "2016D" in sample:
                    jecTag = "Summer16_07Aug2017BCD_V11_DATA"
                elif "2016E" in sample or "2016F" in sample:
                    jecTag = "Summer16_07Aug2017EF_V11_DATA"
                elif "2016G" in sample or "2016H" in sample:
                    jecTag = "Summer16_07Aug2017GH_V11_DATA"
                else:
                    raise ValueError(f"Could not deduce data JEC tag for sample {sample}")
        elif era == "2017":
            if isMC:
                jecTag = "Fall17_17Nov2017_V32_MC"
                smearTag = "Fall17_V3_MC"
                jesUncertaintySources = ["Total"]
            else:
                if "2017B" in sample:
                    jecTag = "Fall17_17Nov2017B_V32_DATA"
                elif "2017C" in sample:
                    jecTag = "Fall17_17Nov2017C_V32_DATA"
                elif "2017D" in sample or "2017E" in sample:
                    jecTag = "Fall17_17Nov2017DE_V32_DATA"
                elif "2017F" in sample:
                    jecTag = "Fall17_17Nov2017F_V32_DATA"
                else:
                    raise ValueError(f"Could not deduce data JEC tag for sample {sample}")
        ## always-on event weights
        if isMC:
            mcWgts = [ tree.genWeight ]
            if puWeightsFile:
                from bamboo.analysisutils import makePileupWeight
                mcWgts.append(makePileupWeight(puWeightsFile, tree.Pileup_nTrueInt, variation="Nominal",
                    nameHint="bamboo_puWeight{0}".format("".join(c for c in sample if c.isalnum()))))
            else:
                logger.warning("Running on MC without pileup reweighting")
            noSel = noSel.refine("mcWeight", weight=mcWgts)
        ## configure corrections and variations
        from bamboo.analysisutils import configureJets, configureType1MET, configureRochesterCorrection
        try:
            configureJets(tree._Jet, "AK4PFchs", jec=jecTag, smear=smearTag, jesUncertaintySources=jesUncertaintySources, mayWriteCache=isNotWorker, isMC=isMC, backend=be, uName=sample)
        except Exception as ex:
            logger.exception("Problem while configuring jet correction and variations")
        try:
            configureType1MET(getattr(tree, f"_{metName}"), jec=jecTag, smear=smearTag, jesUncertaintySources=jesUncertaintySources, mayWriteCache=isNotWorker, isMC=isMC, backend=be, uName=sample)
        except Exception as ex:
            logger.exception("Problem while configuring MET correction and variations")
        try:
            configureRochesterCorrection(tree._Muon, rochesterFile, isMC=isMC, backend=be, uName=sample)
        except Exception as ex:
            logger.exception("Problem while configuring the Rochester correction")

        return tree,noSel,be,lumiArgs

    def definePlots(self, t, noSel, sample=None, sampleCfg=None):
        from bamboo.plots import Plot, SummedPlot, EquidistantBinning
        from bamboo import treefunctions as op
        from bamboo.analysisutils import forceDefine

        era = sampleCfg.get("era") if sampleCfg else None

        plots = []

        ## calculate (corrected) muon 4-momenta before accessing them
        forceDefine(t._Muon.calcProd, noSel)

        muons = op.select(t.Muon, lambda mu : mu.pt > 20.)

        twoMuSel = noSel.refine("twoMuons", cut=[ op.rng_len(muons) > 1 ])
        plots.append(Plot.make1D("dimu_M", op.invariant_mass(muons[0].p4, muons[1].p4), twoMuSel,
                EquidistantBinning(100, 20., 120.), title="Dimuon invariant mass", plotopts={"show-overflow":False}))

        ## evaluate jet and MET for all events passing twoMuSel
        ## more optimization will be needed with systematics etc.
        forceDefine(t._Jet.calcProd, twoMuSel)
        forceDefine(getattr(t, "_{0}".format("MET" if era != "2017" else "METFixEE2017")).calcProd, twoMuSel)

        jets = op.select(t.Jet, lambda j : j.pt > 20.)
        plots.append(Plot.make1D("nJets", op.rng_len(jets), twoMuSel,
                EquidistantBinning(10, 0., 10.), title="Number of jets"))

        twoMuTwoJetSel = twoMuSel.refine("twoMuonsTwoJets", cut=[ op.rng_len(jets) > 1 ])

        leadjpt = Plot.make1D("leadJetPT", jets[0].pt, twoMuTwoJetSel,
                EquidistantBinning(50, 0., 250.), title="Leading jet PT")
        subleadjpt = Plot.make1D("subleadJetPT", jets[1].pt, twoMuTwoJetSel,
                EquidistantBinning(50, 0., 250.), title="Subleading jet PT")
        plots += [ leadjpt, subleadjpt, SummedPlot("twoLeadJetPT", [leadjpt, subleadjpt], xTitle="Leading two jet PTs") ]
        met = t.MET if era != "2017" else t.METFixEE2017
        plots.append(Plot.make1D("MET", met.pt, twoMuTwoJetSel,
                EquidistantBinning(50, 0., 250.), title="MET PT"))

        return plots

class SkimNanoZMuMu(NanoAODSkimmerModule):
    def __init__(self, args):
        super(SkimNanoZMuMu, self).__init__(args)
    def defineSkimSelection(self, tree, noSel, sample=None, sampleCfg=None):
        from bamboo import treefunctions as op
        muons = op.select(tree.Muon, lambda mu : op.AND(mu.pt > 20., op.abs(mu.eta) < 2.4))
        hasTwoMu = noSel.refine("hasTwoMu", cut=(op.rng_len(muons) >= 2))
        varsToKeep = {"nMuon": None, "Muon_eta": None, "Muon_pt": None} ## from input file
        varsToKeep["nSelMuons"] = op.static_cast("UInt_t", op.rng_len(muons)) ## TBranch doesn't accept size_t
        varsToKeep["selMu_miniPFRelIsoNeu"] = op.map(muons, lambda mu : mu.miniPFRelIso_all - mu.miniPFRelIso_chg)
        return hasTwoMu, varsToKeep
