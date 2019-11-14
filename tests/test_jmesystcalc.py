import pytest
import os.path

testData = os.path.join(os.path.dirname(__file__), "data")

@pytest.fixture(scope="module")
def nanojetargsMC16():
    from bamboo.root import gbl
    f = gbl.TFile.Open(os.path.join(testData, "DY_M50_2016.root"))
    tup = f.Get("Events")
    tup.GetEntry(0)
    i = 0
    while tup.nJet < 5:
        i += 1
        tup.GetEntry(i)
    RVec_float = getattr(gbl, "ROOT::VecOps::RVec<float>")
    jet_pt   = RVec_float(tup.Jet_pt, tup.nJet)
    jet_eta  = RVec_float(tup.Jet_eta, tup.nJet)
    jet_phi  = RVec_float(tup.Jet_phi, tup.nJet)
    jet_mass = RVec_float(tup.Jet_mass, tup.nJet)
    jet_rawFactor = RVec_float(tup.Jet_rawFactor, tup.nJet)
    jet_area = RVec_float(tup.Jet_area, tup.nJet)
    genjet_pt   = RVec_float(tup.GenJet_pt, tup.nJet)
    genjet_eta  = RVec_float(tup.GenJet_eta, tup.nJet)
    genjet_phi  = RVec_float(tup.GenJet_phi, tup.nJet)
    genjet_mass = RVec_float(tup.GenJet_mass, tup.nJet)
    yield (jet_pt, jet_eta, jet_phi, jet_mass,
           jet_rawFactor, jet_area, tup.fixedGridRhoFastjetAll,
           tup.MET_phi, tup.MET_pt, tup.MET_sumEt,
           genjet_pt, genjet_eta, genjet_phi, genjet_mass)

@pytest.fixture(scope="module")
def jmesystcalc_empty():
    from bamboo.root import gbl, loadJMESystematicsCalculator
    import bamboo.treefunctions
    loadJMESystematicsCalculator()
    calc = gbl.JMESystematicsCalculator()
    yield calc

@pytest.fixture(scope="module")
def jmesystcalcMC16_smear():
    from bamboo.root import gbl, loadJMESystematicsCalculator
    import bamboo.treefunctions
    loadJMESystematicsCalculator()
    calc = gbl.JMESystematicsCalculator()
    calc.setSmearing(os.path.join(testData, "Summer16_25nsV1_MC_PtResolution_AK4PFchs.txt"), os.path.join(testData, "Summer16_25nsV1_MC_SF_AK4PFchs.txt"), True, 0.2, 3.)
    yield calc

@pytest.fixture(scope="module")
def jmesystcalcMC16_jec():
    from bamboo.root import gbl, loadJMESystematicsCalculator
    import bamboo.treefunctions
    loadJMESystematicsCalculator()
    calc = gbl.JMESystematicsCalculator()
    jecParams = getattr(gbl, "std::vector<JetCorrectorParameters>")()
    l1Param = gbl.JetCorrectorParameters(os.path.join(testData, "Summer16_07Aug2017_V11_MC_L1FastJet_AK4PFchs.txt"))
    l2Param = gbl.JetCorrectorParameters(os.path.join(testData, "Summer16_07Aug2017_V11_MC_L2Relative_AK4PFchs.txt"))
    jecParams.push_back(l1Param)
    jecParams.push_back(l2Param)
    calc.setJEC(jecParams)
    calc.setSmearing(os.path.join(testData, "Summer16_25nsV1_MC_PtResolution_AK4PFchs.txt"), os.path.join(testData, "Summer16_25nsV1_MC_SF_AK4PFchs.txt"), True, 0.2, 3.)
    yield calc

@pytest.fixture(scope="module")
def jmesystcalcMC16_jesunc():
    from bamboo.root import gbl, loadJMESystematicsCalculator
    import bamboo.treefunctions
    loadJMESystematicsCalculator()
    calc = gbl.JMESystematicsCalculator()
    jecParams = getattr(gbl, "std::vector<JetCorrectorParameters>")()
    l1Param = gbl.JetCorrectorParameters(os.path.join(testData, "Summer16_07Aug2017_V11_MC_L1FastJet_AK4PFchs.txt"))
    l2Param = gbl.JetCorrectorParameters(os.path.join(testData, "Summer16_07Aug2017_V11_MC_L2Relative_AK4PFchs.txt"))
    jecParams.push_back(l1Param)
    jecParams.push_back(l2Param)
    calc.setJEC(jecParams)
    calc.setSmearing(os.path.join(testData, "Summer16_25nsV1_MC_PtResolution_AK4PFchs.txt"), os.path.join(testData, "Summer16_25nsV1_MC_SF_AK4PFchs.txt"), True, 0.2, 3.)
    ## uncertaintysources?
    for jus in ["AbsoluteStat", "AbsoluteScale"]:
        param = gbl.JetCorrectorParameters(os.path.join(testData, "Summer16_07Aug2017_V11_MC_UncertaintySources_AK4PFchs.txt"), jus)
        calc.addJESUncertainty(jus, param)
    yield calc

def test_jmesystcalc_empty(jmesystcalc_empty):
    assert jmesystcalc_empty

def test_jmesystcalcMC16_smear(jmesystcalcMC16_smear):
    assert jmesystcalcMC16_smear

def test_jmesystcalcMC16_nano_smear(jmesystcalcMC16_smear, nanojetargsMC16):
    res = jmesystcalcMC16_smear.produceModifiedCollections(*nanojetargsMC16)
    assert res

def test_jmesystcalcMC16_nano_jec(jmesystcalcMC16_jec, nanojetargsMC16):
    res = jmesystcalcMC16_jec.produceModifiedCollections(*nanojetargsMC16)
    assert res

def test_jmesystcalcMC16_nano_jesunc(jmesystcalcMC16_jesunc, nanojetargsMC16):
    res = jmesystcalcMC16_jesunc.produceModifiedCollections(*nanojetargsMC16)
    assert res
