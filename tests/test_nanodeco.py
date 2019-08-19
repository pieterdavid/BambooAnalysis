import pytest

import os.path
testData = os.path.join(os.path.dirname(__file__), "data")

@pytest.fixture(scope="module")
def decoNano():
    from bamboo import treefunctions as op
    from cppyy import gbl
    f = gbl.TFile.Open(os.path.join(testData, "DY_M50_2016.root"))
    tree = f.Get("Events")
    from bamboo.treedecorators import decorateNanoAOD
    from bamboo.dataframebackend import DataframeBackend
    tup = decorateNanoAOD(tree, isMC=True)
    be, noSel = DataframeBackend.create(tup)
    jetcalcName = be.symbol("JMESystematicsCalculator <<name>>{};", nameHint="bamboo_jmeSystCalc")
    tup._Jet.initCalc(op.extVar("JMESystematicsCalculator", jetcalcName), calcHandle=getattr(gbl, jetcalcName))
    roccorName = be.symbol("RochesterCorrectionCalculator <<name>>{};", nameHint="bamboo_roccorCalc")
    tup._Muon.initCalc(op.extVar("RochesterCorrectionCalculator", roccorName), calcHandle=getattr(gbl, roccorName))
    yield tup

def test_getSimpleObjects(decoNano):
    assert decoNano.Electron[0]
    assert decoNano.Muon[0]
    assert decoNano.Photon[0]
    assert decoNano.SubJet[0]
    assert decoNano.FatJet[0]

def test_getJet(decoNano):
    assert decoNano.Jet[0]

def test_simpleRef(decoNano):
    assert decoNano.Electron[0].photon
    assert decoNano.FatJet[0].subJet1

def test_toJetRef(decoNano):
    assert decoNano.Electron[0].jet
    assert decoNano.Muon[0].jet

def test_fromJetRef(decoNano):
    jet = decoNano.Jet[0]
    assert jet.muon1
    assert jet.muon2
    assert jet.electron1
    assert jet.electron2

def test_selectElectron(decoNano):
    from bamboo import treefunctions as op
    ele1 = op.select(decoNano.Electron, lambda ele : op.AND(ele.cutBased_Sum16 >= 3, ele.p4.Pt() > 15.))
    assert ele1.op and ele1[0].p4.Pt().op

def test_selectJet(decoNano):
    from bamboo import treefunctions as op
    jets = op.select(decoNano.Jet, lambda j : op.AND(j.p4.Pt() > 20., op.abs(j.p4.Eta()) < 2.4, j.jetId & 2))
    assert jets.op and jets[0].p4.Pt().op

def test_selectSelectElectron(decoNano):
    from bamboo import treefunctions as op
    ele1 = op.select(decoNano.Electron, lambda ele : op.AND(ele.cutBased_Sum16 >= 3, ele.p4.Pt() > 15.))
    ele2 = op.select(ele1, lambda ele : op.abs(ele.p4.Eta()) < 2.5)
    assert ele1.op and ele2.op and ele2[0].p4.Pt().op

def test_rangeOps_cleanJetsSortReduceCombine(decoNano):
    from bamboo import treefunctions as op
    electrons = op.select(decoNano.Electron, lambda ele : op.AND(ele.cutBased_Sum16 >= 3, ele.p4.Pt() > 15., op.abs(ele.p4.Eta()) < 2.4))
    muons = op.select(decoNano.Muon, lambda mu : op.AND(mu.p4.Pt() > 10., op.abs(mu.p4.Eta()) < 2.4, mu.mediumId, mu.pfRelIso04_all < 0.15))
    jets = op.select(decoNano.Jet, lambda j : op.AND(j.p4.Pt() > 20., op.abs(j.p4.Eta()) < 2.4, j.jetId & 2))
    cleanedJets = op.select(jets, lambda j : op.AND(op.NOT(op.rng_any(electrons, lambda ele : op.deltaR(j.p4, ele.p4) < 0.3 )), op.NOT(op.rng_any(muons, lambda mu : op.deltaR(j.p4, mu.p4) < 0.3 ))))
    cleanedJetsByDeepFlav = op.sort(cleanedJets, lambda jet: jet.btagDeepFlavB)
    prodBTags = op.rng_product(cleanedJets, lambda jet: jet.btagDeepB)
    osdiele  = op.combine(electrons, N=2, pred=lambda ele1,ele2 : ele1.charge != ele2.charge)
    assert electrons.op and muons.op and jets.op and cleanedJets.op and cleanedJets[0].p4.Pt().op and cleanedJetsByDeepFlav.op and cleanedJetsByDeepFlav[0].p4.Pt().op and prodBTags.op and osdiele.op and osdiele[0][1].p4.Pt().op
