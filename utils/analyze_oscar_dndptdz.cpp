//
// Produces (1/Nevt) dN/(dpT dz_h) vs pT in fixed z_h slices for:
//   pi+, pi-, K+, K-
//
// Example:
//   c++ -std=c++17 -O3 -march=native -Wall -Wextra -pedantic analyze_oscar_dndptdz.cpp -o analyze_oscar_dndptdz

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
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

  double width() const { return (xmax - xmin) / nbins; }

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
    int ibin = static_cast<int>((x - xmin) / width());
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
};

enum class FrameChoice { LAB, TRF, BREIT };

constexpr std::size_t NSPEC = 4;
constexpr std::size_t NZ = 4;
constexpr std::array<double, NZ + 1> Z_EDGES = {0.2, 0.3, 0.4, 0.6, 0.8};

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
    case 321: return 2;
    case -321: return 3;
    default: return -1;
  }
}

const char* specTag(std::size_t i) {
  switch (i) {
    case 0: return "pip";
    case 1: return "pim";
    case 2: return "kp";
    case 3: return "km";
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

struct Config {
  std::string metaPath;
  std::string outPath = "dndptdz.yoda";
  double ptMin = 0.0;
  double ptMax = 1.1;
  int ptNBins = 20;
  FrameChoice frame = FrameChoice::BREIT;
  std::vector<std::string> oscarPaths;
  std::vector<std::string> fileListPaths;
};

void printUsage(const char* argv0) {
  std::cerr
      << "Usage: " << argv0 << " --meta DISKinematics.meta.jsonl [options] file1.oscar [file2.oscar ...]\n"
      << "\nOptions:\n"
      << "  --file-list PATH    Read OSCAR input paths from PATH; use '-' for stdin\n"
      << "  --out PATH          Output YODA-like histogram file (default: dndptdz.yoda)\n"
      << "  --pt-min VALUE      pT histogram minimum in GeV (default: 0.0)\n"
      << "  --pt-max VALUE      pT histogram maximum in GeV (default: 1.1)\n"
      << "  --pt-nbins N        Number of pT bins (default: 20)\n"
      << "  --frame NAME        pT frame: LAB, TRF, or BREIT (default: BREIT)\n"
      << "  --help              Show this help\n";
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
    } else if (arg == "--frame") {
      cfg.frame = parseFrame(requireValue(arg));
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


struct AnalysisState {
  std::array<std::array<Hist1D, NZ>, NSPEC> h;
  std::size_t eventsSeen = 0;
  std::size_t eventsWithMeta = 0;
  std::size_t eventsVetoed = 0;
  std::size_t filled = 0;
  std::size_t particlesSeen = 0;
  std::size_t malformedParticleLines = 0;
};

void analyzeParticle(const Particle& particle, const MetaDIS& meta, FrameChoice frame, AnalysisState& state) {
  ++state.particlesSeen;

  const int is = speciesIndex(particle.pdg);
  if (is < 0) return;

  const double Pdotq = minkowskiDot(meta.P, meta.q);
  if (!std::isfinite(Pdotq) || Pdotq == 0.0) return;

  const double zh = minkowskiDot(meta.P, particle.p) / Pdotq;
  if (!std::isfinite(zh)) return;

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

  const int iz = zbinIndex(zh);
  if (iz < 0) return;

  FourVec phLab = particle.p;
  FourVec qLab = meta.q;
  FourVec PLab = meta.P;
  toFrame(FrameChoice::LAB, phLab, qLab, PLab);
  const double phAbs = mag(p3(phLab));
  if (!std::isfinite(phAbs) || phAbs < 2.0 || phAbs > 15.0) return;

  FourVec ph = particle.p;
  FourVec q = meta.q;
  FourVec P = meta.P;
  toFrame(frame, ph, q, P);

  const double pT2 = pT2WrtQ(ph, q);
  if (!std::isfinite(pT2) || pT2 < 0.0) return;
  state.h[static_cast<std::size_t>(is)][static_cast<std::size_t>(iz)].fill(std::sqrt(pT2), 1.0);
  ++state.filled;
}

void analyzeOscarFile(const std::string& path, const std::unordered_map<int, MetaDIS>& meta, FrameChoice frame,
                      AnalysisState& state) {
  std::ifstream in(path);
  if (!in) throw std::runtime_error("Cannot open OSCAR file: " + path);

  std::string line;
  int currentEvent = -1;
  int filenameEvent = -1;
  const bool hasFilenameEvent = eventIdFromFilename(path, filenameEvent);
  const MetaDIS* currentMeta = nullptr;
  bool inEvent = false;

  while (std::getline(in, line)) {
    //line = trim(line);
    if (line.empty()) continue;

    int eventNumber = -1;
    if (parseEventHeader(line, eventNumber)) {
      ++state.eventsSeen;
      currentEvent = hasFilenameEvent ? filenameEvent : eventNumber;
      const auto it = meta.find(currentEvent);
      if (it == meta.end()) {
        ++state.eventsVetoed;
        currentMeta = nullptr;
      } else {
        ++state.eventsWithMeta;
        currentMeta = &it->second;
      }
      inEvent = true;
      continue;
    }

    if (isEventEnd(line)) {
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
    analyzeParticle(particle, *currentMeta, frame, state);
  }
}

void finalize(AnalysisState& state) {
  const double nEvents = state.eventsWithMeta > 0 ? static_cast<double>(state.eventsWithMeta) : 1.0;
  for (std::size_t is = 0; is < NSPEC; ++is) {
    for (std::size_t iz = 0; iz < NZ; ++iz) {
      Hist1D& h = state.h[is][iz];
      h.scale(1.0 / nEvents);
      const double dz = Z_EDGES[iz + 1] - Z_EDGES[iz];
      const double densityFactor = 1.0 / (h.width() * dz);
      h.scaleBinsOnly(densityFactor);
    }
  }
}

void writeHist(std::ostream& out, const Hist1D& h, const std::string& path, double scaledBy) {
  double totalW = 0.0;
  double totalW2 = 0.0;
  double totalWX = 0.0;
  double totalWX2 = 0.0;
  double totalEntries = 0.0;
  for (int i = 0; i < h.nbins; ++i) {
    totalW += h.sumw[i];
    totalW2 += h.sumw2[i];
    totalWX += h.sumwx[i];
    totalWX2 += h.sumwx2[i];
    totalEntries += h.entries[i];
  }

  const double mean = totalW != 0.0 ? totalWX / totalW : 0.0;
  const double area = totalW * h.width();

  out << "BEGIN YODA_HISTO1D_V2 " << path << "\n";
  out << "Path: " << path << "\n";
  out << "ScaledBy: " << std::setprecision(18) << scaledBy << "\n";
  out << "Title:\n";
  out << "Type: Histo1D\n";
  out << "---\n";
  out << "# Mean: " << std::scientific << std::setprecision(6) << mean << "\n";
  out << "# Area: " << std::scientific << std::setprecision(6) << area << "\n";
  out << "# ID\t ID\t sumw\t sumw2\t sumwx\t sumwx2\t numEntries\n";
  out << "Total   \tTotal   \t" << totalW << "\t" << totalW2 << "\t" << totalWX << "\t" << totalWX2
      << "\t" << totalEntries << "\n";
  out << "Underflow\tUnderflow\t" << h.underflow << "\t" << h.underflow2 << "\t" << h.underflowX << "\t"
      << h.underflowX2 << "\t" << h.underflowEntries << "\n";
  out << "Overflow\tOverflow\t" << h.overflow << "\t" << h.overflow2 << "\t" << h.overflowX << "\t"
      << h.overflowX2 << "\t" << h.overflowEntries << "\n";
  out << "# xlow\t xhigh\t sumw\t sumw2\t sumwx\t sumwx2\t numEntries\n";

  for (int i = 0; i < h.nbins; ++i) {
    const double xlow = h.xmin + i * h.width();
    const double xhigh = xlow + h.width();
    out << xlow << "\t" << xhigh << "\t" << h.sumw[i] << "\t" << h.sumw2[i] << "\t" << h.sumwx[i]
        << "\t" << h.sumwx2[i] << "\t" << h.entries[i] << "\n";
  }
  out << "END YODA_HISTO1D_V2\n\n";
}

void writeOutput(const std::string& path, const AnalysisState& state) {
  std::ofstream out(path);
  if (!out) throw std::runtime_error("Cannot write output file: " + path);

  const double scaledBy = state.eventsWithMeta > 0 ? 1.0 / static_cast<double>(state.eventsWithMeta) : 1.0;
  for (std::size_t is = 0; is < NSPEC; ++is) {
    for (std::size_t iz = 0; iz < NZ; ++iz) {
      const std::string histPath = std::string("/EHIJING_SMASH_DNDPTDZ/dN_dptdz_") + specTag(is) + "_" + zTag(iz);
      writeHist(out, state.h[is][iz], histPath, scaledBy);
    }
  }
}

}  // namespace

int main(int argc, char** argv) {
  try {
    const Config cfg = parseArgs(argc, argv);
    auto meta = loadMeta(cfg.metaPath);

    AnalysisState state;
    for (std::size_t is = 0; is < NSPEC; ++is) {
      for (std::size_t iz = 0; iz < NZ; ++iz) {
        state.h[is][iz] = Hist1D(cfg.ptNBins, cfg.ptMin, cfg.ptMax);
      }
    }

    const std::size_t total = cfg.oscarPaths.size();

    for (std::size_t i = 0; i < total; ++i) {
        analyzeOscarFile(cfg.oscarPaths[i], meta, cfg.frame, state);

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
    writeOutput(cfg.outPath, state);

    std::cerr << "Loaded metadata entries: " << meta.size() << "\n";
    std::cerr << "Events seen:            " << state.eventsSeen << "\n";
    std::cerr << "Events with metadata:   " << state.eventsWithMeta << "\n";
    std::cerr << "Events vetoed:          " << state.eventsVetoed << "\n";
    std::cerr << "Particles seen:         " << state.particlesSeen << "\n";
    std::cerr << "Filled entries:         " << state.filled << "\n";
    std::cerr << "Malformed lines:        " << state.malformedParticleLines << "\n";
    std::cerr << "Wrote:                  " << cfg.outPath << "\n";
  } catch (const std::exception& ex) {
    std::cerr << "error: " << ex.what() << "\n\n";
    printUsage(argv[0]);
    return 1;
  }

  return 0;
}
