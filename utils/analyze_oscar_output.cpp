//
// Produces both:
//   (1/Nevt) dN/(dpT dz_h) vs pT in fixed z_h slices, and
//   (1/Nevt) dN/dz_h vs z_h, integrated over transverse momentum, for:
//   pi+, pi-, pi0, K+, K-, p, pbar
// Also produces:
//   (1/Nevt) dN/(dQ2 dz_h) vs Q2 in fixed z_h slices, and
//   (1/Nevt) dN/(dxB dz_h) vs xB in fixed z_h slices.
//   (1/Nevt) dN/dnu and (1/Nevt) dN/dQ2, integrated over z_h and pT.
// Default z_h, nu, and Q2 axes match HERMES arXiv:0704.3270, Fig. 2.
// Additional /HERMES_2007 histograms apply the Fig. 2 selection and retain
// per-bin DIS denominators and event-level hadron-count second moments.
//
// Example:
//   c++ -std=c++17 -O3 -Wall -Wextra -pedantic utils/analyze_oscar_output.cpp -o analyze_oscar_output

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace {

struct Vec3 {
  double x = 0.0;
  double y = 0.0;
  double z = 0.0;
};

struct FourVec {
  double E = 0.0;
  double px = 0.0;
  double py = 0.0;
  double pz = 0.0;
};

struct MetaDIS {
  int event = -1;
  int Z = 0;
  int A = 0;
  double xB = std::numeric_limits<double>::quiet_NaN();
  double Q2 = std::numeric_limits<double>::quiet_NaN();
  double y = std::numeric_limits<double>::quiet_NaN();
  double nu = std::numeric_limits<double>::quiet_NaN();
  FourVec P;
  FourVec q;
};

struct Particle {
  double mass = 0.0;
  FourVec p;
  int pdg = 0;
};

struct Hist1D {
  double xmin = 0.0;
  double xmax = 0.0;
  int nbins = 0;
  std::vector<double> sumw;
  std::vector<double> sumw2;
  std::vector<double> sumwx;
  std::vector<double> sumwx2;
  std::vector<double> entries;
  std::vector<double> edges;
  double underflow = 0.0;
  double overflow = 0.0;
  double underflow2 = 0.0;
  double overflow2 = 0.0;
  double underflowX = 0.0;
  double overflowX = 0.0;
  double underflowX2 = 0.0;
  double overflowX2 = 0.0;
  double underflowEntries = 0.0;
  double overflowEntries = 0.0;

  Hist1D() = default;
  Hist1D(int n, double lo, double hi)
      : xmin(lo), xmax(hi), nbins(n), sumw(n, 0.0), sumw2(n, 0.0), sumwx(n, 0.0),
        sumwx2(n, 0.0), entries(n, 0.0) {}

  explicit Hist1D(const std::vector<double>& binEdges) {
    if (binEdges.size() < 2) {
      throw std::runtime_error("Hist1D explicit bin edges must contain at least two values");
    }
    for (std::size_t i = 1; i < binEdges.size(); ++i) {
      if (!std::isfinite(binEdges[i - 1]) || !std::isfinite(binEdges[i]) ||
          binEdges[i] <= binEdges[i - 1]) {
        throw std::runtime_error("Hist1D explicit bin edges must be finite and strictly increasing");
      }
    }
    xmin = binEdges.front();
    xmax = binEdges.back();
    nbins = static_cast<int>(binEdges.size()) - 1;
    sumw.assign(nbins, 0.0);
    sumw2.assign(nbins, 0.0);
    sumwx.assign(nbins, 0.0);
    sumwx2.assign(nbins, 0.0);
    entries.assign(nbins, 0.0);
    edges = binEdges;
  }

  double width() const { return (xmax - xmin) / nbins; }
  double width(int ibin) const {
    if (edges.empty()) return width();
    return edges[static_cast<std::size_t>(ibin) + 1] - edges[static_cast<std::size_t>(ibin)];
  }
  double lowEdge(int ibin) const {
    if (edges.empty()) return xmin + ibin * width();
    return edges[static_cast<std::size_t>(ibin)];
  }
  double highEdge(int ibin) const {
    if (edges.empty()) return xmin + (ibin + 1) * width();
    return edges[static_cast<std::size_t>(ibin) + 1];
  }

  void fill(double x, double w = 1.0) {
    if (!std::isfinite(x) || !std::isfinite(w)) return;
    if (x < xmin) {
      underflow += w;
      underflow2 += w * w;
      underflowX += w * x;
      underflowX2 += w * x * x;
      underflowEntries += 1.0;
      return;
    }
    if (x >= xmax) {
      overflow += w;
      overflow2 += w * w;
      overflowX += w * x;
      overflowX2 += w * x * x;
      overflowEntries += 1.0;
      return;
    }
    int ibin = 0;
    if (edges.empty()) {
      ibin = static_cast<int>((x - xmin) / width());
    } else {
      const auto it = std::upper_bound(edges.begin(), edges.end(), x);
      ibin = static_cast<int>(std::distance(edges.begin(), it)) - 1;
    }
    ibin = std::max(0, std::min(nbins - 1, ibin));
    sumw[ibin] += w;
    sumw2[ibin] += w * w;
    sumwx[ibin] += w * x;
    sumwx2[ibin] += w * x * x;
    entries[ibin] += 1.0;
  }

  void scale(double factor) {
    const double factor2 = factor * factor;
    for (int i = 0; i < nbins; ++i) {
      sumw[i] *= factor;
      sumw2[i] *= factor2;
      sumwx[i] *= factor;
      sumwx2[i] *= factor;
    }
    underflow *= factor;
    overflow *= factor;
    underflow2 *= factor2;
    overflow2 *= factor2;
    underflowX *= factor;
    overflowX *= factor;
    underflowX2 *= factor;
    overflowX2 *= factor;
  }

  void scaleBinsOnly(double factor) {
    const double factor2 = factor * factor;
    for (int i = 0; i < nbins; ++i) {
      sumw[i] *= factor;
      sumw2[i] *= factor2;
      sumwx[i] *= factor;
      sumwx2[i] *= factor;
    }
  }

  void scaleBinOnly(int ibin, double factor) {
    const double factor2 = factor * factor;
    sumw[ibin] *= factor;
    sumw2[ibin] *= factor2;
    sumwx[ibin] *= factor;
    sumwx2[ibin] *= factor;
  }
};

enum class FrameChoice { LAB, TRF, BREIT };

constexpr std::size_t NSPEC = 7;
constexpr std::size_t NZ = 4;
constexpr std::array<double, NZ + 1> Z_EDGES = {0.2, 0.3, 0.4, 0.6, 0.8};
// HERMES Fig. 2 bin boundaries, from HEPData 10.17182/hepdata.13387.v1
// (Tables 1, 4, and 8). Z_EDGES above retains the existing double-differential slices.
constexpr std::array<double, 10> ZH_EDGES = {0.1, 0.2, 0.3, 0.4, 0.5,
                                           0.6, 0.7, 0.8, 0.9, 1.3};
constexpr std::array<double, 10> NU_EDGES = {4.0, 6.0, 8.0, 10.0, 12.0,
                                           14.0, 16.0, 18.0, 20.0, 23.5};
constexpr std::size_t NQ2 = 8;
constexpr std::array<double, NQ2 + 1> Q2_EDGES = {1.0, 1.5, 2.0, 3.0, 4.0,
                                                5.0, 6.0, 8.0, 25.0};
constexpr std::size_t NXB = 9;
constexpr std::array<double, NXB + 1> XB_EDGES = {0.023, 0.04, 0.055, 0.075, 0.1,
                                                  0.14, 0.2, 0.3, 0.4, 0.6};
constexpr bool PRINT_PER_PARTICLE_DEBUG = false;
constexpr bool APPLY_XF_CUT = false;
constexpr bool APPLY_PID_MOMENTUM_CUT = false;

double dot(const Vec3& a, const Vec3& b) {
  return a.x * b.x + a.y * b.y + a.z * b.z;
}

double mag2(const Vec3& v) {
  return dot(v, v);
}

double mag(const Vec3& v) {
  return std::sqrt(mag2(v));
}

Vec3 p3(const FourVec& p) {
  return {p.px, p.py, p.pz};
}

double minkowskiDot(const FourVec& a, const FourVec& b) {
  return a.E * b.E - a.px * b.px - a.py * b.py - a.pz * b.pz;
}

void boostBy(FourVec& p, const Vec3& beta) {
  const double b2 = mag2(beta);
  if (b2 <= 0.0) return;
  if (b2 >= 1.0) return;

  const double gamma = 1.0 / std::sqrt(1.0 - b2);
  const Vec3 pv = p3(p);
  const double bp = dot(beta, pv);
  const double gamma2 = (gamma - 1.0) / b2;
  const double oldE = p.E;

  p.E = gamma * (oldE + bp);
  p.px += (gamma2 * bp + gamma * oldE) * beta.x;
  p.py += (gamma2 * bp + gamma * oldE) * beta.y;
  p.pz += (gamma2 * bp + gamma * oldE) * beta.z;
}

void toFrame(FrameChoice frame, FourVec& ph, FourVec& q, FourVec& P) {
  if (frame == FrameChoice::LAB) return;

  if (P.E <= 0.0) return;
  const Vec3 bTRF{-P.px / P.E, -P.py / P.E, -P.pz / P.E};
  boostBy(ph, bTRF);
  boostBy(q, bTRF);
  boostBy(P, bTRF);

  if (frame == FrameChoice::TRF) return;

  const Vec3 qv = p3(q);
  const double qmag = mag(qv);
  if (qmag == 0.0) return;

  const double beta = q.E / qmag;
  if (!std::isfinite(beta) || std::abs(beta) >= 1.0) return;

  const Vec3 bBreit{beta * qv.x / qmag, beta * qv.y / qmag, beta * qv.z / qmag};
  boostBy(ph, bBreit);
  boostBy(q, bBreit);
  boostBy(P, bBreit);
}

double pT2WrtQ(const FourVec& ph, const FourVec& q) {
  const Vec3 qv = p3(q);
  const double qmag = mag(qv);
  if (qmag == 0.0) return 0.0;

  const Vec3 pv = p3(ph);
  const double ppar = dot(pv, qv) / qmag;
  const Vec3 pT{pv.x - ppar * qv.x / qmag,
                pv.y - ppar * qv.y / qmag,
                pv.z - ppar * qv.z / qmag};
  return mag2(pT);
}

double feynmanX(const FourVec& ph, const FourVec& P, const FourVec& q) {
  FourVec H{P.E + q.E, P.px + q.px, P.py + q.py, P.pz + q.pz};
  const double W2 = minkowskiDot(H, H);
  if (!std::isfinite(W2) || W2 <= 0.0 || H.E <= 0.0) return std::numeric_limits<double>::quiet_NaN();

  const double W = std::sqrt(W2);
  const Vec3 beta{-H.px / H.E, -H.py / H.E, -H.pz / H.E};

  FourVec phStar = ph;
  FourVec qStar = q;
  boostBy(phStar, beta);
  boostBy(qStar, beta);

  const Vec3 qv = p3(qStar);
  const double qmag = mag(qv);
  if (!std::isfinite(qmag) || qmag == 0.0) return std::numeric_limits<double>::quiet_NaN();

  const double pL = dot(p3(phStar), qv) / qmag;
  return 2.0 * pL / W;
}

/*
  std::string trim(const std::string& s) {
  std::size_t first = 0;
  while (first < s.size() && std::isspace(static_cast<unsigned char>(s[first]))) ++first;
  std::size_t last = s.size();
  while (last > first && std::isspace(static_cast<unsigned char>(s[last - 1]))) --last;
  return s.substr(first, last - first);
}
*/

std::vector<std::string> readJsonObjects(const std::string& path) {
  std::ifstream in(path);
  if (!in) throw std::runtime_error("Cannot open metadata file: " + path);

  std::vector<std::string> objects;
  std::string line;
  std::string buf;
  int depth = 0;
  bool started = false;
  bool inString = false;
  bool escape = false;

  while (std::getline(in, line)) {
    for (char c : line) {
      if (!started) {
        if (std::isspace(static_cast<unsigned char>(c))) continue;
        if (c == '{') {
          started = true;
          depth = 1;
          buf.clear();
          buf.push_back(c);
          inString = false;
          escape = false;
        }
        continue;
      }

      buf.push_back(c);
      if (escape) {
        escape = false;
        continue;
      }
      if (c == '\\' && inString) {
        escape = true;
        continue;
      }
      if (c == '"') {
        inString = !inString;
        continue;
      }
      if (inString) continue;

      if (c == '{') ++depth;
      if (c == '}') --depth;
      if (depth == 0) {
        objects.push_back(buf);
        buf.clear();
        started = false;
      }
    }
    if (started) buf.push_back('\n');
  }

  if (started || depth != 0) {
    throw std::runtime_error("Metadata file has unbalanced JSON object braces: " + path);
  }
  return objects;
}

std::size_t findKey(const std::string& js, const std::string& key) {
  const std::string quoted = "\"" + key + "\"";
  const std::size_t pos = js.find(quoted);
  if (pos == std::string::npos) throw std::runtime_error("Missing metadata key: " + key);
  return pos + quoted.size();
}

double parseNumberAfter(const std::string& js, std::size_t pos) {
  const std::size_t colon = js.find(':', pos);
  if (colon == std::string::npos) throw std::runtime_error("Malformed JSON number");
  std::size_t first = colon + 1;
  while (first < js.size() && std::isspace(static_cast<unsigned char>(js[first]))) ++first;
  char* end = nullptr;
  const double value = std::strtod(js.c_str() + first, &end);
  if (end == js.c_str() + first || !std::isfinite(value)) {
    throw std::runtime_error("Failed to parse JSON number");
  }
  return value;
}

double getNumber(const std::string& js, const std::string& key) {
  return parseNumberAfter(js, findKey(js, key));
}

std::array<double, 4> getArray4(const std::string& js, const std::string& key) {
  const std::size_t keyEnd = findKey(js, key);
  const std::size_t colon = js.find(':', keyEnd);
  const std::size_t open = js.find('[', colon);
  const std::size_t close = js.find(']', open);
  if (colon == std::string::npos || open == std::string::npos || close == std::string::npos) {
    throw std::runtime_error("Malformed JSON 4-vector for key: " + key);
  }

  std::array<double, 4> values{};
  std::size_t pos = open + 1;
  for (double& value : values) {
    while (pos < close && (std::isspace(static_cast<unsigned char>(js[pos])) || js[pos] == ',')) ++pos;
    char* end = nullptr;
    value = std::strtod(js.c_str() + pos, &end);
    if (end == js.c_str() + pos || !std::isfinite(value)) {
      throw std::runtime_error("Failed to parse JSON 4-vector for key: " + key);
    }
    pos = static_cast<std::size_t>(end - js.c_str());
  }
  return values;
}

std::unordered_map<int, MetaDIS> loadMeta(const std::string& path) {
  std::unordered_map<int, MetaDIS> meta;
  for (const std::string& js : readJsonObjects(path)) {
    MetaDIS m;
    m.event = static_cast<int>(getNumber(js, "event"));
    m.Z = static_cast<int>(getNumber(js, "Z"));
    m.A = static_cast<int>(getNumber(js, "A"));
    m.xB = getNumber(js, "xB");
    m.Q2 = getNumber(js, "Q2");
    m.y = getNumber(js, "y");
    m.nu = getNumber(js, "nu");
    const auto P4 = getArray4(js, "P4");
    const auto q4 = getArray4(js, "q4");
    m.P = {P4[3], P4[0], P4[1], P4[2]};
    m.q = {q4[3], q4[0], q4[1], q4[2]};
    meta.emplace(m.event, m);
  }
  if (meta.empty()) throw std::runtime_error("Metadata file had zero parsed events: " + path);
  return meta;
}

std::vector<std::string> readPathList(const std::string& path) {
    std::istream* in = nullptr;
    std::ifstream file;

    if (path == "-") {
        in = &std::cin;
    } else {
        file.open(path);
        if (!file) throw std::runtime_error("Cannot open file list: " + path);
        in = &file;
    }

    std::vector<std::string> paths;
    std::string line;

    while (std::getline(*in, line)) {
        //line = trim(line);
        if (line.empty()) continue;
        if (line[0] == '#') continue;
        paths.push_back(line);
    }

    if (paths.empty()) {
        throw std::runtime_error("File list is empty: " + path);
    }

    return paths;
}

int speciesIndex(int pdg) {
  switch (pdg) {
    case 211: return 0;
    case -211: return 1;
    case 111: return 2;
    case 321: return 3;
    case -321: return 4;
    case 2212: return 5;
    case -2212: return 6;
    default: return -1;
  }
}

double minHadronMomentum(int pdg) {
  const int absPdg = std::abs(pdg);
  if (absPdg == 211) return 1.0;
  if (absPdg == 321) return 2.0;
  return 0.0;
}

const char* specTag(std::size_t i) {
  switch (i) {
    case 0: return "pip";
    case 1: return "pim";
    case 2: return "pi0";
    case 3: return "kp";
    case 4: return "km";
    case 5: return "p";
    case 6: return "pbar";
    default: return "unk";
  }
}

const char* zTag(std::size_t i) {
  switch (i) {
    case 0: return "zh0p2_0p3";
    case 1: return "zh0p3_0p4";
    case 2: return "zh0p4_0p6";
    case 3: return "zh0p6_0p8";
    default: return "zhX";
  }
}

int zbinIndex(double zh) {
  for (std::size_t i = 0; i < NZ; ++i) {
    if (zh > Z_EDGES[i] && zh < Z_EDGES[i + 1]) return static_cast<int>(i);
  }
  return -1;
}

FrameChoice parseFrame(const std::string& frame) {
  if (frame == "LAB" || frame == "lab") return FrameChoice::LAB;
  if (frame == "TRF" || frame == "trf") return FrameChoice::TRF;
  if (frame == "BREIT" || frame == "breit") return FrameChoice::BREIT;
  throw std::runtime_error("Unknown frame '" + frame + "'. Expected LAB, TRF, or BREIT.");
}

const char* frameName(FrameChoice frame) {
  switch (frame) {
    case FrameChoice::LAB: return "LAB";
    case FrameChoice::TRF: return "TRF";
    case FrameChoice::BREIT: return "BREIT";
  }
  return "UNKNOWN";
}

struct Config {
  std::string metaPath;
  std::string outPath = "dndptdz_dndz.yoda";
  double ptMin = 0.0;
  double ptMax = 1.1;
  int ptNBins = 20;
  double zhMin = 0.05;
  double zhMax = 1.05;
  int zhNBins = 10;
  bool uniformZhBins = false;
  bool hermesAngularAcceptance = false;
  double hermesBeamEnergy = 27.6;
  int hermesBeamDirection = -1;
  double xfMin = 0.0;
  double xfMax = std::numeric_limits<double>::infinity();
  FrameChoice frame = FrameChoice::BREIT;
  std::vector<std::string> oscarPaths;
  std::vector<std::string> fileListPaths;
};

void printUsage(const char* argv0) {
  std::cerr
      << "Usage: " << argv0 << " --meta DISKinematics.meta.jsonl [options] file1.oscar [file2.oscar ...]\n"
      << "\nOptions:\n"
      << "  --file-list PATH    Read OSCAR input paths from PATH; use '-' for stdin\n"
      << "  --out PATH          Output YODA-like histogram file (default: dndptdz_dndz.yoda)\n"
      << "  --pt-min VALUE      pT histogram minimum in GeV (default: 0.0)\n"
      << "  --pt-max VALUE      pT histogram maximum in GeV (default: 1.1)\n"
      << "  --pt-nbins N        Number of pT bins (default: 20)\n"
      << "  --zh-min VALUE      Override with a uniform z_h axis; minimum (fallback: 0.05)\n"
      << "  --zh-max VALUE      Override with a uniform z_h axis; maximum (fallback: 1.05)\n"
      << "  --zh-nbins N        Override with a uniform z_h axis; bin count (fallback: 10)\n"
      << "  --xf-min VALUE      Legacy spectra xF minimum (inactive in current build; 0.0)\n"
      << "  --xf-max VALUE      Legacy spectra xF maximum (inactive in current build; no upper cut)\n"
      << "  --frame NAME        pT frame: LAB, TRF, or BREIT (default: BREIT)\n"
      << "  --hermes-acceptance NAME  rectangular or none (default), for /HERMES_2007 only\n"
      << "  --hermes-beam-energy E    Incoming lepton energy in target rest frame (GeV; 27.6)\n"
      << "  --hermes-beam-direction AXIS  Incoming lepton axis: -z (default) or +z\n"
      << "  --help              Show this help\n"
      << "\nDefault axes (HERMES arXiv:0704.3270, Fig. 2):\n"
      << "  z_h: 0.1 0.2 0.3 0.4 0.5 0.6 0.7 0.8 0.9 1.3\n"
      << "  nu [GeV]: 4 6 8 10 12 14 16 18 20 23.5\n"
      << "  Q2 [GeV^2]: 1 1.5 2 3 4 5 6 8 25\n"
      << "Any --zh-* option selects a uniform z_h axis for the generic spectra.\n"
      << "/HERMES_2007 outputs always use the fixed Fig. 2 cuts and binning.\n";
}

Config parseArgs(int argc, char** argv) {
  Config cfg;
  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    auto requireValue = [&](const std::string& opt) -> std::string {
      if (i + 1 >= argc) throw std::runtime_error("Missing value for " + opt);
      return argv[++i];
    };

    if (arg == "--help" || arg == "-h") {
      printUsage(argv[0]);
      std::exit(0);
    } else if (arg == "--meta") {
      cfg.metaPath = requireValue(arg);
    } else if (arg == "--file-list") {
      cfg.fileListPaths.push_back(requireValue(arg));
    } else if (arg == "--out") {
      cfg.outPath = requireValue(arg);
    } else if (arg == "--pt-min") {
      cfg.ptMin = std::stod(requireValue(arg));
    } else if (arg == "--pt-max") {
      cfg.ptMax = std::stod(requireValue(arg));
    } else if (arg == "--pt-nbins") {
      cfg.ptNBins = std::stoi(requireValue(arg));
    } else if (arg == "--zh-min") {
      cfg.uniformZhBins = true;
      cfg.zhMin = std::stod(requireValue(arg));
    } else if (arg == "--zh-max") {
      cfg.uniformZhBins = true;
      cfg.zhMax = std::stod(requireValue(arg));
    } else if (arg == "--zh-nbins") {
      cfg.uniformZhBins = true;
      cfg.zhNBins = std::stoi(requireValue(arg));
    } else if (arg == "--xf-min") {
      cfg.xfMin = std::stod(requireValue(arg));
    } else if (arg == "--xf-max") {
      cfg.xfMax = std::stod(requireValue(arg));
    } else if (arg == "--frame") {
      cfg.frame = parseFrame(requireValue(arg));
    } else if (arg == "--hermes-acceptance") {
      const std::string value = requireValue(arg);
      if (value != "rectangular" && value != "none") {
        throw std::runtime_error("--hermes-acceptance must be rectangular or none");
      }
      cfg.hermesAngularAcceptance = value == "rectangular";
    } else if (arg == "--hermes-beam-energy") {
      cfg.hermesBeamEnergy = std::stod(requireValue(arg));
    } else if (arg == "--hermes-beam-direction") {
      const std::string value = requireValue(arg);
      if (value != "-z" && value != "+z") {
        throw std::runtime_error("--hermes-beam-direction must be -z or +z");
      }
      cfg.hermesBeamDirection = value == "-z" ? -1 : 1;
    } else if (!arg.empty() && arg[0] == '-') {
      throw std::runtime_error("Unknown option: " + arg);
    } else {
      cfg.oscarPaths.push_back(arg);
    }
  }

  if (cfg.metaPath.empty()) throw std::runtime_error("Missing required --meta path");
  for (const std::string& listPath : cfg.fileListPaths) {
      std::vector<std::string> listed = readPathList(listPath);
      cfg.oscarPaths.insert(cfg.oscarPaths.end(), listed.begin(), listed.end());
  }
  if (cfg.oscarPaths.empty()) throw std::runtime_error("Provide at least one OSCAR file");

  if (!std::isfinite(cfg.ptMin) || !std::isfinite(cfg.ptMax) || cfg.ptMax <= cfg.ptMin) {
    throw std::runtime_error("Invalid pT axis: require finite --pt-max > --pt-min");
  }
  if (cfg.ptNBins <= 0) throw std::runtime_error("--pt-nbins must be positive");
  if (!std::isfinite(cfg.zhMin) || !std::isfinite(cfg.zhMax) || cfg.zhMax <= cfg.zhMin) {
    throw std::runtime_error("Invalid z_h axis: require finite --zh-max > --zh-min");
  }
  if (cfg.zhNBins <= 0) throw std::runtime_error("--zh-nbins must be positive");
  if (!std::isfinite(cfg.xfMin)) throw std::runtime_error("--xf-min must be finite");
  if (!std::isfinite(cfg.hermesBeamEnergy) || cfg.hermesBeamEnergy <= 0.000511) {
    throw std::runtime_error("--hermes-beam-energy must exceed the electron mass");
  }
  if (std::isnan(cfg.xfMax) || cfg.xfMax <= cfg.xfMin) {
    throw std::runtime_error("Invalid Feynman x cut: require --xf-max > --xf-min");
  }
  return cfg;
}

bool parseEventHeader(const std::string& line, int& eventNumber) {
  std::istringstream iss(line);
  std::string hash;
  std::string word;
  if (!(iss >> hash >> word)) return false;
  if (hash != "#" || word != "event") return false;
  if (!(iss >> eventNumber)) return false;
  return line.find(" out ") != std::string::npos;
}

bool eventIdFromFilename(const std::string& path, int& eventNumber) {

  const std::string prefix = "event_";

  std::size_t pos = 0;
  while ((pos = path.find(prefix, pos)) != std::string::npos) {
      const std::size_t digitStart = pos + prefix.size();
      std::size_t digitEnd = digitStart;

      while (digitEnd < path.size() &&
              std::isdigit(static_cast<unsigned char>(path[digitEnd]))) {
          ++digitEnd;
      }

      if (digitEnd > digitStart) {
          const bool goodEnd =
              digitEnd == path.size() ||
              path[digitEnd] == '.' ||
              path[digitEnd] == '/' ||
              path[digitEnd] == '\\';

          if (goodEnd) {
              eventNumber = std::stoi(path.substr(digitStart, digitEnd - digitStart));
              return true;
          }
    }
      pos = digitEnd;
    }
  return false;
    }


bool isEventEnd(const std::string& line) {
  return line.rfind("# event ", 0) == 0 && line.find(" end ") != std::string::npos;
}

bool parseParticleLine(const std::string& line, Particle& particle) {

    const char* p = line.c_str();
    char* end = nullptr;

    auto nextDouble = [&]() -> double {
        double v = std::strtod(p, &end);
        if (end == p) throw std::runtime_error("bad_double");
        p = end;
        return v;
    };

    auto nextInt = [&]() -> int {
        long v = std::strtol(p, &end, 10);
        if (end == p) throw std::runtime_error("bad int");
        p = end;
        return static_cast<int>(v);
    };

    try {
        const double t = nextDouble();
        const double x = nextDouble();
        const double y = nextDouble();
        const double z = nextDouble();
        (void)t; (void)x; (void)y; (void)z;

        particle.mass = nextDouble();
        particle.p.E = nextDouble();
        particle.p.px = nextDouble();
        particle.p.py = nextDouble();
        particle.p.pz = nextDouble();
        particle.pdg = nextInt();

        const int id = nextInt();
        const int charge = nextInt();
        (void)id;
        (void)charge;
    } catch (...) {
        return false;
    }

    return true;

}


struct HermesState {
  std::array<Hist1D, NSPEC> z;
  std::array<Hist1D, NSPEC> nu;
  std::array<Hist1D, NSPEC> q2;
  Hist1D disZ{std::vector<double>(ZH_EDGES.begin(), ZH_EDGES.end())};
  Hist1D disNu{std::vector<double>(NU_EDGES.begin(), NU_EDGES.end())};
  Hist1D disQ2{std::vector<double>(Q2_EDGES.begin(), Q2_EDGES.end())};
  std::size_t acceptedDIS = 0;

  HermesState() {
    for (std::size_t is = 0; is < NSPEC; ++is) {
      z[is] = Hist1D(std::vector<double>(ZH_EDGES.begin(), ZH_EDGES.end()));
      nu[is] = Hist1D(std::vector<double>(NU_EDGES.begin(), NU_EDGES.end()));
      q2[is] = Hist1D(std::vector<double>(Q2_EDGES.begin(), Q2_EDGES.end()));
    }
  }
};

struct HermesEvent {
  bool accepted = false;
  std::array<std::array<double, ZH_EDGES.size() - 1>, NSPEC> z{};
  std::array<std::array<double, NU_EDGES.size() - 1>, NSPEC> nu{};
  std::array<std::array<double, Q2_EDGES.size() - 1>, NSPEC> q2{};
};

template <std::size_t N>
int edgeBin(double x, const std::array<double, N>& edges) {
  if (!std::isfinite(x) || x < edges.front() || x >= edges.back()) return -1;
  return static_cast<int>(std::upper_bound(edges.begin(), edges.end(), x) - edges.begin()) - 1;
}

bool inHermesAcceptance(const FourVec& p, const Config& cfg) {
  const double longitudinal = cfg.hermesBeamDirection * p.pz;
  if (longitudinal <= 0.0 || !std::isfinite(longitudinal)) return false;
  const double tx = std::abs(std::atan2(p.px, longitudinal));
  const double ty = std::abs(std::atan2(p.py, longitudinal));
  return tx < 0.170 && ty > 0.040 && ty < 0.140;
}

bool passesHermesDIS(const MetaDIS& meta, const Config& cfg) {
  const FourVec total{meta.P.E + meta.q.E, meta.P.px + meta.q.px,
                      meta.P.py + meta.q.py, meta.P.pz + meta.q.pz};
  if (!(meta.Q2 > 1.0 && minkowskiDot(total, total) > 4.0 &&
        meta.y > 0.0 && meta.y < 0.85 && meta.nu > 0.0)) return false;
  if (!cfg.hermesAngularAcceptance) return true;

  // q = k - k'. Beam energy and signed z axis are specified in the target rest frame.
  FourVec dummy, q = meta.q, P = meta.P;
  toFrame(FrameChoice::TRF, dummy, q, P);
  constexpr double electronMass = 0.00051099895;
  const double beamP = std::sqrt(cfg.hermesBeamEnergy * cfg.hermesBeamEnergy - electronMass * electronMass);
  const FourVec scattered{cfg.hermesBeamEnergy - q.E, -q.px, -q.py,
                          cfg.hermesBeamDirection * beamP - q.pz};
  return scattered.E > electronMass && inHermesAcceptance(scattered, cfg);
}

void analyzeHermesParticle(const Particle& particle, const MetaDIS& meta,
                          const Config& cfg, HermesEvent& event) {
  if (!event.accepted) return;
  const int species = speciesIndex(particle.pdg);
  if (species < 0) return;
  const double Pdotq = minkowskiDot(meta.P, meta.q);
  if (!(Pdotq > 0.0)) return;
  const double zh = minkowskiDot(meta.P, particle.p) / Pdotq;
  const double xf = feynmanX(particle.p, meta.P, meta.q);
  if (!std::isfinite(zh) || !std::isfinite(xf) || xf <= 0.0) return;

  FourVec ph = particle.p, q = meta.q, P = meta.P;
  toFrame(FrameChoice::TRF, ph, q, P);
  const double momentum = mag(p3(ph));
  const double minimum = particle.pdg == 111 ? 2.5 : 2.0;
  if (!std::isfinite(momentum) || momentum <= minimum || momentum >= 15.0) return;
  if (cfg.hermesAngularAcceptance && !inHermesAcceptance(ph, cfg)) return;

  const auto is = static_cast<std::size_t>(species);
  const int iz = edgeBin(zh, ZH_EDGES);
  const int inu = edgeBin(meta.nu, NU_EDGES);
  const int iq2 = edgeBin(meta.Q2, Q2_EDGES);
  if (meta.nu > 6.0 && zh > 0.1 && iz >= 0) ++event.z[is][iz];
  if (meta.nu > 4.0 && zh > 0.2 && inu >= 0) ++event.nu[is][inu];
  if (meta.nu > 6.0 && zh > 0.2 && iq2 >= 0) ++event.q2[is][iq2];
}

void finishHermesEvent(const HermesEvent& event, const MetaDIS& meta, HermesState& state) {
  if (!event.accepted) return;
  ++state.acceptedDIS;
  if (meta.nu > 4.0) state.disNu.fill(meta.nu);
  if (meta.nu > 6.0) {
    state.disQ2.fill(meta.Q2);
    // Every z bin uses the same inclusive DIS sample, including zero-hadron events.
    for (int ib = 0; ib < state.disZ.nbins; ++ib) {
      state.disZ.fill(0.5 * (state.disZ.lowEdge(ib) + state.disZ.highEdge(ib)));
    }
  }
  for (std::size_t is = 0; is < NSPEC; ++is) {
    for (auto pair : {std::make_pair(&state.z[is], event.z[is].data()),
                      std::make_pair(&state.nu[is], event.nu[is].data()),
                      std::make_pair(&state.q2[is], event.q2[is].data())}) {
      Hist1D& h = *pair.first;
      for (int ib = 0; ib < h.nbins; ++ib) {
        if (pair.second[ib] > 0.0) {
          // One weighted fill per event/bin: sumw2 records sum of squared event counts.
          h.fill(0.5 * (h.lowEdge(ib) + h.highEdge(ib)), pair.second[ib]);
        }
      }
    }
  }
}

struct AnalysisState {
  HermesState hermes;
  std::array<std::array<Hist1D, NZ>, NSPEC> hPtZ;
  std::array<std::array<Hist1D, NZ>, NSPEC> hQ2Z;
  std::array<std::array<Hist1D, NZ>, NSPEC> hXBZ;
  std::array<Hist1D, NSPEC> hZ;
  std::array<Hist1D, NSPEC> hNu;
  std::array<Hist1D, NSPEC> hQ2;
  std::size_t eventsSeen = 0;
  std::size_t eventsWithMeta = 0;
  std::size_t eventsVetoed = 0;
  std::size_t filledPtZ = 0;
  std::size_t filledQ2Z = 0;
  std::size_t filledXBZ = 0;
  std::size_t filledZ = 0;
  std::size_t filledNu = 0;
  std::size_t filledQ2 = 0;
  std::size_t particlesSeen = 0;
  std::size_t particlesRejectedXF = 0;
  std::size_t malformedParticleLines = 0;
};

void printParticleDebug(const Particle& particle, const MetaDIS& meta, FrameChoice frame,
                        double zh, double pT, const std::string& status,
                        const std::string& reason) {
  if (!PRINT_PER_PARTICLE_DEBUG) return;
  if (particle.pdg != 211) return;
  if (status != "filled") return;

  std::cerr << std::setprecision(12)
            << "[new-analyzer-debug] event=" << meta.event
            << " pdg=" << particle.pdg
            << " zh=" << zh
            << " E=" << particle.p.E
            << " px=" << particle.p.px
            << " py=" << particle.p.py
            << " pz=" << particle.p.pz
            << " pT_frame=" << frameName(frame)
            << " pT=" << pT
            << " status=" << status
            << " reason=\"" << reason << "\""
            << "\n";
}

void analyzeParticle(const Particle& particle, const MetaDIS& meta, const Config& cfg, AnalysisState& state) {
  ++state.particlesSeen;

  const double Pdotq = minkowskiDot(meta.P, meta.q);
  if (!std::isfinite(Pdotq) || Pdotq == 0.0) {
    printParticleDebug(particle, meta, cfg.frame, std::numeric_limits<double>::quiet_NaN(),
                       std::numeric_limits<double>::quiet_NaN(), "cut", "invalid P.q");
    return;
  }

  const double zh = minkowskiDot(meta.P, particle.p) / Pdotq;
  if (!std::isfinite(zh)) {
    printParticleDebug(particle, meta, cfg.frame, zh, std::numeric_limits<double>::quiet_NaN(),
                       "cut", "invalid zh");
    return;
  }

  const int is = speciesIndex(particle.pdg);
  if (is < 0) {
    printParticleDebug(particle, meta, cfg.frame, zh, std::numeric_limits<double>::quiet_NaN(),
                       "cut", "PDG not tracked");
    return;
  }

  if (APPLY_XF_CUT) {
    const double xf = feynmanX(particle.p, meta.P, meta.q);
    if (!std::isfinite(xf)) {
      printParticleDebug(particle, meta, cfg.frame, zh, std::numeric_limits<double>::quiet_NaN(),
                         "cut", "invalid xF");
      return;
    }
    if (xf < cfg.xfMin || xf > cfg.xfMax) {
      ++state.particlesRejectedXF;
      printParticleDebug(particle, meta, cfg.frame, zh, std::numeric_limits<double>::quiet_NaN(),
                         "cut", "outside xF range");
      return;
    }
  }

  FourVec phTRF = particle.p;
  FourVec qTRF = meta.q;
  FourVec PTRF = meta.P;
  toFrame(FrameChoice::TRF, phTRF, qTRF, PTRF);
  const double zhTRF = phTRF.E / qTRF.E;
  if (std::isfinite(zhTRF) && std::abs(zh - zhTRF) > 1e-6) {
    static int warnings = 0;
    if (warnings < 10) {
      std::cerr << "warning: zh mismatch for PDG " << particle.pdg << ": P.p/P.q=" << zh
                << " E_h/nu=" << zhTRF << "\n";
      ++warnings;
    }
  }

  if (APPLY_PID_MOMENTUM_CUT) {
    FourVec phLab = particle.p;
    const double phAbs = mag(p3(phLab));
    const double phMin = minHadronMomentum(particle.pdg);
    if (!std::isfinite(phAbs) || phAbs <= phMin || phAbs >= 15.0) {
      printParticleDebug(particle, meta, cfg.frame, zh, std::numeric_limits<double>::quiet_NaN(),
                         "cut", "outside species Ph range");
      return;
    }
  }

  state.hZ[static_cast<std::size_t>(is)].fill(zh, 1.0);
  ++state.filledZ;
  state.hNu[static_cast<std::size_t>(is)].fill(meta.nu, 1.0);
  ++state.filledNu;
  state.hQ2[static_cast<std::size_t>(is)].fill(meta.Q2, 1.0);
  ++state.filledQ2;

  const int iz = zbinIndex(zh);
  if (iz >= 0) {
    if (std::isfinite(meta.Q2)) {
      state.hQ2Z[static_cast<std::size_t>(is)][static_cast<std::size_t>(iz)].fill(meta.Q2, 1.0);
      ++state.filledQ2Z;
    }
    if (std::isfinite(meta.xB)) {
      state.hXBZ[static_cast<std::size_t>(is)][static_cast<std::size_t>(iz)].fill(meta.xB, 1.0);
      ++state.filledXBZ;
    }
  }

  FourVec ph = particle.p;
  FourVec q = meta.q;
  FourVec P = meta.P;
  toFrame(cfg.frame, ph, q, P);

  const double pT2 = pT2WrtQ(ph, q);
  const double pT = (std::isfinite(pT2) && pT2 >= 0.0)
                       ? std::sqrt(pT2)
                       : std::numeric_limits<double>::quiet_NaN();
  if (!std::isfinite(pT)) {
    printParticleDebug(particle, meta, cfg.frame, zh, pT, "cut", "invalid pT");
    return;
  }

  std::string status = iz >= 0 ? "filled" : "cut";
  std::string reason = iz >= 0 ? "none" : "outside fixed zh slices";
  if (iz >= 0 && (pT < cfg.ptMin || pT >= cfg.ptMax)) {
    status = "cut";
    reason = "outside pT histogram bins";
  }
  printParticleDebug(particle, meta, cfg.frame, zh, pT, status, reason);

  if (iz >= 0) {
    state.hPtZ[static_cast<std::size_t>(is)][static_cast<std::size_t>(iz)].fill(pT, 1.0);
    ++state.filledPtZ;
  }
}

void analyzeOscarFile(const std::string& path, const std::unordered_map<int, MetaDIS>& meta, const Config& cfg,
                      AnalysisState& state) {
  std::ifstream in(path);
  if (!in) throw std::runtime_error("Cannot open OSCAR file: " + path);

  std::string line;
  int currentEvent = -1;
  int filenameEvent = -1;
  const bool hasFilenameEvent = eventIdFromFilename(path, filenameEvent);
  const MetaDIS* currentMeta = nullptr;
  bool inEvent = false;
  HermesEvent hermesEvent;

  while (std::getline(in, line)) {
    //line = trim(line);
    if (line.empty()) continue;

    int eventNumber = -1;
    if (parseEventHeader(line, eventNumber)) {
      if (inEvent) throw std::runtime_error("Multiple out blocks before event end in " + path +
                                            "; supply final-only OSCAR particle lists");
      hermesEvent = HermesEvent{};
      ++state.eventsSeen;
      currentEvent = hasFilenameEvent ? filenameEvent : eventNumber;
      const auto it = meta.find(currentEvent);
      if (it == meta.end()) {
        ++state.eventsVetoed;
        currentMeta = nullptr;
      } else {
        ++state.eventsWithMeta;
        currentMeta = &it->second;
        hermesEvent.accepted = passesHermesDIS(*currentMeta, cfg);
      }
      inEvent = true;
      continue;
    }

    if (isEventEnd(line)) {
      if (inEvent && currentMeta) finishHermesEvent(hermesEvent, *currentMeta, state.hermes);
      inEvent = false;
      currentEvent = -1;
      currentMeta = nullptr;
      continue;
    }

    if (!inEvent || !currentMeta || line[0] == '#') continue;

    Particle particle;
    if (!parseParticleLine(line, particle)) {
      ++state.malformedParticleLines;
      continue;
    }
    analyzeParticle(particle, *currentMeta, cfg, state);
    analyzeHermesParticle(particle, *currentMeta, cfg, hermesEvent);
  }
  if (inEvent) throw std::runtime_error("Unterminated OSCAR event in " + path);
}

void finalize(AnalysisState& state) {
  const double nEvents = state.eventsWithMeta > 0 ? static_cast<double>(state.eventsWithMeta) : 1.0;
  for (std::size_t is = 0; is < NSPEC; ++is) {
    for (std::size_t iz = 0; iz < NZ; ++iz) {
      Hist1D& h = state.hPtZ[is][iz];
      h.scale(1.0 / nEvents);
      const double dz = Z_EDGES[iz + 1] - Z_EDGES[iz];
      const double densityFactor = 1.0 / (h.width() * dz);
      h.scaleBinsOnly(densityFactor);

      Hist1D& hq2 = state.hQ2Z[is][iz];
      hq2.scale(1.0 / nEvents);
      for (int ib = 0; ib < hq2.nbins; ++ib) {
        hq2.scaleBinOnly(ib, 1.0 / (hq2.width(ib) * dz));
      }

      Hist1D& hxb = state.hXBZ[is][iz];
      hxb.scale(1.0 / nEvents);
      for (int ib = 0; ib < hxb.nbins; ++ib) {
        hxb.scaleBinOnly(ib, 1.0 / (hxb.width(ib) * dz));
      }
    }
    for (Hist1D* h : {&state.hZ[is], &state.hNu[is], &state.hQ2[is]}) {
      h->scale(1.0 / nEvents);
      for (int ib = 0; ib < h->nbins; ++ib) {
        h->scaleBinOnly(ib, 1.0 / h->width(ib));
      }
    }
  }
}

void writeHist(std::ostream& out, const Hist1D& h, const std::string& path, double scaledBy,
               const std::string& annotations = "") {
  double totalW = 0.0;
  double totalW2 = 0.0;
  double totalWX = 0.0;
  double totalWX2 = 0.0;
  double totalEntries = 0.0;
  double area = 0.0;
  for (int i = 0; i < h.nbins; ++i) {
    totalW += h.sumw[i];
    totalW2 += h.sumw2[i];
    totalWX += h.sumwx[i];
    totalWX2 += h.sumwx2[i];
    totalEntries += h.entries[i];
    area += h.sumw[i] * h.width(i);
  }

  const double mean = totalW != 0.0 ? totalWX / totalW : 0.0;

  out << "BEGIN YODA_HISTO1D_V2 " << path << "\n";
  out << "Path: " << path << "\n";
  out << "ScaledBy: " << std::setprecision(18) << scaledBy << "\n";
  out << "Title:\n";
  out << "Type: Histo1D\n";
  out << annotations;
  out << "---\n";
  out << "# Mean: " << std::scientific << std::setprecision(6) << mean << "\n";
  out << "# Area: " << std::scientific << std::setprecision(6) << area << "\n";
  // Retain event-count moments accurately when computing a small SEM from a large sample.
  out << std::setprecision(annotations.empty() ? 6 : 17);
  out << "# ID\t ID\t sumw\t sumw2\t sumwx\t sumwx2\t numEntries\n";
  out << "Total   \tTotal   \t" << totalW << "\t" << totalW2 << "\t" << totalWX << "\t" << totalWX2
      << "\t" << totalEntries << "\n";
  out << "Underflow\tUnderflow\t" << h.underflow << "\t" << h.underflow2 << "\t" << h.underflowX << "\t"
      << h.underflowX2 << "\t" << h.underflowEntries << "\n";
  out << "Overflow\tOverflow\t" << h.overflow << "\t" << h.overflow2 << "\t" << h.overflowX << "\t"
      << h.overflowX2 << "\t" << h.overflowEntries << "\n";
  out << "# xlow\t xhigh\t sumw\t sumw2\t sumwx\t sumwx2\t numEntries\n";

  for (int i = 0; i < h.nbins; ++i) {
    const double xlow = h.lowEdge(i);
    const double xhigh = h.highEdge(i);
    out << xlow << "\t" << xhigh << "\t" << h.sumw[i] << "\t" << h.sumw2[i] << "\t" << h.sumwx[i]
        << "\t" << h.sumwx2[i] << "\t" << h.entries[i] << "\n";
  }
  out << "END YODA_HISTO1D_V2\n\n";
}

void writeHermesOutput(std::ostream& out, const HermesState& state, const Config& cfg) {
  const std::string annotations = "Selection: HERMES_2007_FIG2_V1\nAcceptance: " +
      std::string(cfg.hermesAngularAcceptance ? "rectangular" : "none") +
      "\nBeamEnergyGeV: " + std::to_string(cfg.hermesBeamEnergy) +
      "\nBeamDirection: " + (cfg.hermesBeamDirection < 0 ? "-z" : "+z") + "\n";
  const std::array<const Hist1D*, 3> dis = {&state.disZ, &state.disNu, &state.disQ2};
  const std::array<const std::array<Hist1D, NSPEC>*, 3> hadrons = {&state.z, &state.nu, &state.q2};
  const std::array<std::string, 3> names = {"zh", "nu", "Q2"};
  for (std::size_t axis = 0; axis < names.size(); ++axis) {
    const std::string base = "/HERMES_2007/" + names[axis];
    writeHist(out, *dis[axis], base + "/DIS", 1.0, annotations);
    for (std::size_t is = 0; is < NSPEC; ++is) {
      const Hist1D& counts = (*hadrons[axis])[is];
      writeHist(out, counts, base + "/counts_" + specTag(is), 1.0, annotations);
      Hist1D multiplicity = counts;
      for (int ib = 0; ib < counts.nbins; ++ib) {
        const double n = dis[axis]->sumw[ib];
        const double width = axis == 0 ? counts.width(ib) : 1.0;
        const double mean = n > 0.0 ? counts.sumw[ib] / n : 0.0;
        const double variance = n > 1.0
            ? std::max(0.0, counts.sumw2[ib] - counts.sumw[ib] * mean) / (n * (n - 1.0)) : 0.0;
        multiplicity.scaleBinOnly(ib, n > 0.0 ? 1.0 / (n * width) : 0.0);
        multiplicity.sumw2[ib] = variance / (width * width);
      }
      writeHist(out, multiplicity, base + "/multiplicity_" + specTag(is), 1.0, annotations);
    }
  }
}

void writeOutput(const std::string& path, const AnalysisState& state, const Config& cfg) {
  std::ofstream out(path);
  if (!out) throw std::runtime_error("Cannot write output file: " + path);

  const double scaledBy = state.eventsWithMeta > 0 ? 1.0 / static_cast<double>(state.eventsWithMeta) : 1.0;
  for (std::size_t is = 0; is < NSPEC; ++is) {
    for (std::size_t iz = 0; iz < NZ; ++iz) {
      const std::string histPath = std::string("/ELECTRA_MC_2026_DNDPTDZ/dN_dptdz_") + specTag(is) + "_" + zTag(iz);
      writeHist(out, state.hPtZ[is][iz], histPath, scaledBy);
    }
    for (std::size_t iz = 0; iz < NZ; ++iz) {
      const std::string histPath = std::string("/ELECTRA_MC_2026_DNDQ2DZ/dN_dQ2dz_") + specTag(is) + "_" + zTag(iz);
      writeHist(out, state.hQ2Z[is][iz], histPath, scaledBy);
    }
    for (std::size_t iz = 0; iz < NZ; ++iz) {
      const std::string histPath = std::string("/ELECTRA_MC_2026_DNDXBDZ/dN_dxbdz_") + specTag(is) + "_" + zTag(iz);
      writeHist(out, state.hXBZ[is][iz], histPath, scaledBy);
    }
    const std::string histPath = std::string("/ELECTRA_MC_2026_DNDZ/dN_dz_") + specTag(is);
    writeHist(out, state.hZ[is], histPath, scaledBy);
    writeHist(out, state.hNu[is], std::string("/ELECTRA_MC_2026_DNDNU/dN_dnu_") + specTag(is), scaledBy);
    writeHist(out, state.hQ2[is], std::string("/ELECTRA_MC_2026_DNDQ2/dN_dQ2_") + specTag(is), scaledBy);
  }
  writeHermesOutput(out, state.hermes, cfg);
}

}  // namespace

int main(int argc, char** argv) {
  try {
    const Config cfg = parseArgs(argc, argv);
    auto meta = loadMeta(cfg.metaPath);

    AnalysisState state;
    for (std::size_t is = 0; is < NSPEC; ++is) {
      for (std::size_t iz = 0; iz < NZ; ++iz) {
        state.hPtZ[is][iz] = Hist1D(cfg.ptNBins, cfg.ptMin, cfg.ptMax);
        state.hQ2Z[is][iz] = Hist1D(std::vector<double>(Q2_EDGES.begin(), Q2_EDGES.end()));
        state.hXBZ[is][iz] = Hist1D(std::vector<double>(XB_EDGES.begin(), XB_EDGES.end()));
      }
      state.hZ[is] = cfg.uniformZhBins
                        ? Hist1D(cfg.zhNBins, cfg.zhMin, cfg.zhMax)
                        : Hist1D(std::vector<double>(ZH_EDGES.begin(), ZH_EDGES.end()));
      state.hNu[is] = Hist1D(std::vector<double>(NU_EDGES.begin(), NU_EDGES.end()));
      state.hQ2[is] = Hist1D(std::vector<double>(Q2_EDGES.begin(), Q2_EDGES.end()));
    }

    const std::size_t total = cfg.oscarPaths.size();

    for (std::size_t i = 0; i < total; ++i) {
        analyzeOscarFile(cfg.oscarPaths[i], meta, cfg, state);

        if (i % 100 == 0 || i + 1 == total) {
            std::cerr
                << "[progress] "
                << (i + 1) << "/" << total
                << " (" << (100.0 * (i + 1) / total) << "%)"
                << " | events=" << state.eventsSeen
                << '\n';
        }
    }

    finalize(state);
    writeOutput(cfg.outPath, state, cfg);

    std::cerr << "Loaded metadata entries: " << meta.size() << "\n";
    std::cerr << "Events seen:            " << state.eventsSeen << "\n";
    std::cerr << "Events with metadata:   " << state.eventsWithMeta << "\n";
    std::cerr << "Events vetoed:          " << state.eventsVetoed << "\n";
    std::cerr << "HERMES accepted DIS:    " << state.hermes.acceptedDIS << "\n";
    std::cerr << "Particles seen:         " << state.particlesSeen << "\n";
    std::cerr << "Particles rejected xF:  " << state.particlesRejectedXF << "\n";
    std::cerr << "Filled dN/dpT/dz entries: " << state.filledPtZ << "\n";
    std::cerr << "Filled dN/dQ2/dz entries: " << state.filledQ2Z << "\n";
    std::cerr << "Filled dN/dxB/dz entries: " << state.filledXBZ << "\n";
    std::cerr << "Filled dN/dz entries:     " << state.filledZ << "\n";
    std::cerr << "Filled dN/dnu entries:    " << state.filledNu << "\n";
    std::cerr << "Filled dN/dQ2 entries:    " << state.filledQ2 << "\n";
    std::cerr << "Malformed lines:        " << state.malformedParticleLines << "\n";
    std::cerr << "Wrote:                  " << cfg.outPath << "\n";
  } catch (const std::exception& ex) {
    std::cerr << "error: " << ex.what() << "\n\n";
    printUsage(argv[0]);
    return 1;
  }

  return 0;
}
