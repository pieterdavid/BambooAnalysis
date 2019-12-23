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
    seed = (tup.run<<20) + (tup.luminosityBlock<<10) + tup.event + 1 + ( int(tup.Jet_eta[0]/.01) if tup.nJet != 0 else 0)
    genjet_pt   = RVec_float(tup.GenJet_pt, tup.nJet)
    genjet_eta  = RVec_float(tup.GenJet_eta, tup.nJet)
    genjet_phi  = RVec_float(tup.GenJet_phi, tup.nJet)
    genjet_mass = RVec_float(tup.GenJet_mass, tup.nJet)
    yield (jet_pt, jet_eta, jet_phi, jet_mass,
           jet_rawFactor, jet_area, tup.fixedGridRhoFastjetAll,
           seed, genjet_pt, genjet_eta, genjet_phi, genjet_mass)

@pytest.fixture(scope="module")
def nanojetargsMC16_postvalues():
    from bamboo.root import gbl
    f = gbl.TFile.Open(os.path.join(testData, "DY_M50_2016postproc_JMEKin_bTagShape.root"))
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
    seed = (tup.run<<20) + (tup.luminosityBlock<<10) + tup.event + 1 + ( int(tup.Jet_eta[0]/.01) if tup.nJet != 0 else 0)
    genjet_pt   = RVec_float(tup.GenJet_pt, tup.nJet)
    genjet_eta  = RVec_float(tup.GenJet_eta, tup.nJet)
    genjet_phi  = RVec_float(tup.GenJet_phi, tup.nJet)
    genjet_mass = RVec_float(tup.GenJet_mass, tup.nJet)
    ## results to compare to
    jet_vars = {
        "nominal" : (RVec_float(tup.Jet_pt_nom    , tup.nJet), RVec_float(tup.Jet_mass_nom    , tup.nJet)),
        "jerup"   : (RVec_float(tup.Jet_pt_jerUp  , tup.nJet), RVec_float(tup.Jet_mass_jerUp  , tup.nJet)),
        "jerdown" : (RVec_float(tup.Jet_pt_jerDown, tup.nJet), RVec_float(tup.Jet_mass_jerDown, tup.nJet))
        }
    from itertools import chain
    jet_vars.update(dict(chain.from_iterable(
        { "jes{0}up".format(src) : tuple(RVec_float(getattr(tup, "Jet_{0}_jes{1}Up".format(ivar, src)), tup.nJet) for ivar in ("pt", "mass")),
          "jes{0}down".format(src) : tuple(RVec_float(getattr(tup, "Jet_{0}_jes{1}Down".format(ivar, src)), tup.nJet) for ivar in ("pt", "mass")),
        }.items() for src in ("AbsoluteStat", "AbsoluteScale")
        )))
    yield ((jet_pt, jet_eta, jet_phi, jet_mass,
            jet_rawFactor, jet_area, tup.fixedGridRhoFastjetAll,
            seed, genjet_pt, genjet_eta, genjet_phi, genjet_mass),
           jet_vars
          )

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

import math
def isclose_float(a, b):
    from bamboo.root import gbl
    return math.isclose(a, b, rel_tol=2.*getattr(gbl, "std::numeric_limits<float>").epsilon())

def test_jmesystcalc_nanopost_jesunc(jmesystcalcMC16_jesunc, nanojetargsMC16_postvalues):
    nanojetargsMC16, postValues = nanojetargsMC16_postvalues
    res = jmesystcalcMC16_jesunc.produceModifiedCollections(*nanojetargsMC16)
    for ky,(post_pt, post_mass) in postValues.items():
        print(ky, res.at(ky).pt(), post_pt)
        print(ky, res.at(ky).mass(), post_mass)
        assert all(isclose_float(a,b) for a,b in zip(post_pt, res.at(ky).pt())) and all(isclose_float(a,b) for a,b in zip(post_mass, res.at(ky).mass()))
