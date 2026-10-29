// Included inside analyze_oscar_output.cpp's anonymous namespace: shared OSCAR
// reader and kinematics, with no physics dependencies besides yaml-cpp.
#ifdef ELECTRA_WITH_YAML

void writeHist(std::ostream&, const Hist1D&, const std::string&, double, const std::string&);

namespace analysis_yaml {

void keys(const YAML::Node& node, const std::vector<std::string>& allowed, const std::string& where) {
  if (!node.IsMap()) throw std::runtime_error(where + " must be a mapping");
  std::unordered_set<std::string> seen;
  for (const auto& item : node) {
    const auto key = item.first.as<std::string>();
    if (!seen.insert(key).second) throw std::runtime_error(where + ": duplicate key " + key);
    if (std::find(allowed.begin(), allowed.end(), key) == allowed.end()) {
      throw std::runtime_error(where + ": unknown key " + key);
    }
  }
}

double number(const YAML::Node& node) {
  double value;
  try { value = node.as<double>(); }
  catch (const YAML::Exception&) { throw std::runtime_error("Expected a finite YAML number"); }
  if (!std::isfinite(value)) throw std::runtime_error("YAML numeric values must be finite");
  return value;
}

std::string identifier(const YAML::Node& node) {
  const auto value = node.as<std::string>();
  if (value.empty() || !std::all_of(value.begin(), value.end(), [](unsigned char c) {
        return std::isalnum(c) || c == '_' || c == '-';
      })) throw std::runtime_error("Names must contain only letters, digits, '_' or '-'");
  return value;
}

bool eventVariable(const std::string& name) {
  static const std::unordered_set<std::string> names = {
      "Q2", "W2", "W", "xB", "y", "nu", "A", "Z", "lepton_E", "lepton_p",
      "lepton_theta", "lepton_abs_theta_x", "lepton_abs_theta_y"};
  return names.count(name) != 0;
}

void variable(const std::string& name, bool eventOnly = false) {
  static const std::unordered_set<std::string> hadron = {
      "zh", "p", "E", "pT", "pT2", "xF", "theta", "abs_theta_x", "abs_theta_y", "rapidity"};
  if (!eventVariable(name) && (eventOnly || !hadron.count(name))) {
    throw std::runtime_error("Unknown " + std::string(eventOnly ? "event " : "") + "variable: " + name);
  }
}

struct Range {
  double min = -std::numeric_limits<double>::infinity();
  double max = std::numeric_limits<double>::infinity();
  bool minInclusive = false, maxInclusive = false;
  bool contains(double value) const {
    return std::isfinite(value) && (minInclusive ? value >= min : value > min) &&
           (maxInclusive ? value <= max : value < max);
  }
};

using Cuts = std::map<std::string, Range>;

Cuts cuts(const YAML::Node& node, Cuts result, bool eventOnly) {
  if (!node) return result;
  if (!node.IsMap()) throw std::runtime_error("Cuts must be a mapping");
  std::unordered_set<std::string> seen;
  for (const auto& item : node) {
    const auto name = item.first.as<std::string>();
    variable(name, eventOnly);
    if (!seen.insert(name).second) throw std::runtime_error("Duplicate cut: " + name);
    if (item.second.IsNull()) { result.erase(name); continue; }
    keys(item.second, {"min", "max", "min_inclusive", "max_inclusive"}, "cut " + name);
    Range range;
    if (item.second["min"]) range.min = number(item.second["min"]);
    if (item.second["max"]) range.max = number(item.second["max"]);
    if (item.second["min_inclusive"]) range.minInclusive = item.second["min_inclusive"].as<bool>();
    if (item.second["max_inclusive"]) range.maxInclusive = item.second["max_inclusive"].as<bool>();
    if (range.max <= range.min || (!item.second["min"] && !item.second["max"])) {
      throw std::runtime_error("Cut " + name + " requires min < max and at least one bound");
    }
    result[name] = range;
  }
  return result;
}

struct Species {
  std::string name;
  std::vector<int> pdgs;
  std::string charge;
  bool matches(const Particle& particle) const {
    if (!pdgs.empty()) return std::find(pdgs.begin(), pdgs.end(), particle.pdg) != pdgs.end();
    // Inclusive hadrons exclude leptons, photons and nuclear fragments.
    const auto pdg = std::abs(static_cast<long long>(particle.pdg));
    if (pdg < 100 || pdg >= 1000000000) return false;
    return charge == "nonzero" ? particle.charge != 0 :
           charge == "positive" ? particle.charge > 0 : particle.charge < 0;
  }
};

struct Axis {
  std::string variable;
  std::vector<double> edges;
  bool density = false;
  // 0 = underflow, 1..N = regular bins, N+1 = overflow.
  std::size_t bin(double value) const {
    return static_cast<std::size_t>(std::upper_bound(edges.begin(), edges.end(), value) - edges.begin());
  }
};

Axis axis(const YAML::Node& node) {
  keys(node, {"variable", "edges", "min", "max", "bins", "density"}, "axis");
  Axis result;
  result.variable = node["variable"].as<std::string>();
  variable(result.variable);
  if (node["density"]) result.density = node["density"].as<bool>();
  if (node["edges"]) {
    if (node["min"] || node["max"] || node["bins"]) throw std::runtime_error("Use edges OR min/max/bins");
    if (!node["edges"].IsSequence()) throw std::runtime_error("edges must be a sequence");
    for (const auto& edge : node["edges"]) result.edges.push_back(number(edge));
  } else {
    const double lo = number(node["min"]), hi = number(node["max"]);
    const int bins = node["bins"].as<int>();
    if (!(hi > lo) || bins < 1 || bins > 1000000) throw std::runtime_error("Invalid uniform axis");
    for (int i = 0; i <= bins; ++i) result.edges.push_back(lo + (hi - lo) * i / bins);
  }
  Hist1D validate(result.edges);
  return result;
}

struct Cell {
  long double hadrons = 0, squared = 0, weightedCount = 0;
  long double dis = 0, disSquared = 0;
  std::size_t events = 0;
  std::array<long double, 7> profile{};
};

struct Histogram {
  std::string name, kind = "multiplicity", quantity, normalization = "per_dis";
  std::vector<Axis> axes;
  std::vector<Species> species;
  Cuts eventCuts, hadronCuts;
  std::vector<std::size_t> strides;
  std::vector<std::vector<Cell>> cells;
  std::vector<std::vector<double>> eventCounts;
  std::vector<bool> denominators;
  bool accepted = false;
  std::size_t outsideSlices = 0, missingTimeEvents = 0, unavailableTimes = 0;

  std::vector<std::size_t> indices(std::size_t flat) const {
    std::vector<std::size_t> result(axes.size());
    for (std::size_t i = axes.size(); i-- > 0;) {
      result[i] = flat / strides[i];
      flat %= strides[i];
    }
    return result;
  }
};

}  // namespace analysis_yaml

class GenericAnalysis {
  using Cuts = analysis_yaml::Cuts;
  using Histogram = analysis_yaml::Histogram;
  YAML::Node config;
  std::string name, sourceText;
  FrameChoice frame = FrameChoice::TRF;
  double beamEnergy = 0, beamMass = 0, weight = 1;
  int beamDirection = -1;
  std::string weighting = "unit";
  const MetaDIS* meta = nullptr;
  int targetZ = -1, targetA = -1;
  std::vector<Histogram> histograms;

  double angle(const FourVec& p, const std::string& key) const {
    const double longitudinal = beamDirection * p.pz;
    if (key.find("theta_x") != std::string::npos) return std::abs(std::atan2(p.px, longitudinal));
    if (key.find("theta_y") != std::string::npos) return std::abs(std::atan2(p.py, longitudinal));
    return std::atan2(std::hypot(p.px, p.py), longitudinal);
  }

  double value(const std::string& key, const Particle* particle = nullptr) const {
    if (key == "Q2") return meta->Q2;
    if (key == "xB") return meta->xB;
    if (key == "y") return meta->y;
    if (key == "nu") return meta->nu;
    if (key == "A") return meta->A;
    if (key == "Z") return meta->Z;
    if (key == "W" || key == "W2") {
      FourVec total{meta->P.E + meta->q.E, meta->P.px + meta->q.px,
                    meta->P.py + meta->q.py, meta->P.pz + meta->q.pz};
      const double w2 = minkowskiDot(total, total);
      return key == "W2" ? w2 : std::sqrt(w2);
    }
    if (key.rfind("lepton_", 0) == 0) {
      FourVec dummy, q = meta->q, P = meta->P;
      toFrame(FrameChoice::TRF, dummy, q, P);
      FourVec scattered{beamEnergy - q.E, -q.px, -q.py,
          beamDirection * std::sqrt(beamEnergy * beamEnergy - beamMass * beamMass) - q.pz};
      if (scattered.E <= beamMass) return std::numeric_limits<double>::quiet_NaN();
      if (key == "lepton_E") return scattered.E;
      if (key == "lepton_p") return mag(p3(scattered));
      return angle(scattered, key);
    }
    if (!particle) throw std::runtime_error("Hadron variable used for DIS normalization: " + key);
    if (key == "zh") return minkowskiDot(meta->P, particle->p) / minkowskiDot(meta->P, meta->q);
    if (key == "xF") return feynmanX(particle->p, meta->P, meta->q);
    FourVec ph = particle->p, q = meta->q, P = meta->P;
    toFrame(frame, ph, q, P);
    if (key == "p") return mag(p3(ph));
    if (key == "E") return ph.E;
    if (key == "pT2") return pT2WrtQ(ph, q);
    if (key == "pT") return std::sqrt(pT2WrtQ(ph, q));
    if (key == "rapidity") {
      const double parallel = dot(p3(ph), p3(q)) / mag(p3(q));
      return 0.5 * std::log((ph.E + parallel) / (ph.E - parallel));
    }
    return angle(ph, key);
  }

  bool passes(const Cuts& cuts, const Particle* particle = nullptr) const {
    for (const auto& cut : cuts) if (!cut.second.contains(value(cut.first, particle))) return false;
    return true;
  }

 public:
  explicit GenericAnalysis(const std::string& path) {
    using namespace analysis_yaml;
    std::ifstream input(path);
    if (!input) throw std::runtime_error("Cannot read analysis YAML: " + path);
    sourceText.assign(std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>());
    const auto documents = YAML::LoadAll(sourceText);
    if (documents.size() != 1) throw std::runtime_error("Analysis YAML must contain exactly one document");
    config = documents.front();
    keys(config, {"version", "name", "description", "beam", "frame", "weighting", "species",
                  "event_cuts", "hadron_cuts", "histograms"}, "analysis");
    if (config["version"].as<int>() != 1) throw std::runtime_error("Unsupported analysis YAML version");
    name = identifier(config["name"]);
    frame = parseFrame(config["frame"].as<std::string>());
    keys(config["beam"], {"energy", "mass", "direction"}, "beam");
    beamEnergy = number(config["beam"]["energy"]);
    beamMass = number(config["beam"]["mass"]);
    const auto direction = config["beam"]["direction"].as<std::string>();
    if ((direction != "+z" && direction != "-z") || beamMass < 0 || beamEnergy <= beamMass) {
      throw std::runtime_error("beam requires energy > mass >= 0 and direction +z or -z (target rest frame)");
    }
    beamDirection = direction == "-z" ? -1 : 1;
    if (config["weighting"]) weighting = config["weighting"].as<std::string>();
    if (weighting != "unit" && weighting != "metadata") throw std::runtime_error("weighting must be unit or metadata");
    const auto eventCuts = cuts(config["event_cuts"], {}, true);
    const auto hadronCuts = cuts(config["hadron_cuts"], {}, false);
    std::map<std::string, Species> species;
    if (!config["species"].IsMap() || config["species"].size() == 0) throw std::runtime_error("species must be a nonempty mapping");
    for (const auto& item : config["species"]) {
      Species entry;
      entry.name = identifier(item.first);
      if (item.second.IsSequence()) {
        for (const auto& pdg : item.second) {
          const int code = pdg.as<int>();
          if (code == 0 || std::find(entry.pdgs.begin(), entry.pdgs.end(), code) != entry.pdgs.end()) {
            throw std::runtime_error("Species PDG codes must be nonzero and unique");
          }
          entry.pdgs.push_back(code);
        }
        if (entry.pdgs.empty()) throw std::runtime_error("Empty species PDG list");
      } else {
        keys(item.second, {"charge"}, "species " + entry.name);
        entry.charge = item.second["charge"].as<std::string>();
        if (entry.charge != "nonzero" && entry.charge != "positive" && entry.charge != "negative") {
          throw std::runtime_error("Inclusive hadron charge must be nonzero, positive or negative");
        }
      }
      if (!species.emplace(entry.name, entry).second) throw std::runtime_error("Duplicate species name");
    }
    const auto definitions = config["histograms"];
    if (!definitions.IsSequence() || definitions.size() == 0) throw std::runtime_error("histograms must be a nonempty sequence");
    std::unordered_set<std::string> names;
    std::size_t allocatedCells = 0;
    for (const auto& definition : definitions) {
      keys(definition, {"name", "kind", "quantity", "normalization", "species", "event_cuts", "hadron_cuts", "axes"}, "histogram");
      Histogram h;
      h.name = identifier(definition["name"]);
      if (!names.insert(h.name).second) throw std::runtime_error("Duplicate histogram name: " + h.name);
      h.eventCuts = cuts(definition["event_cuts"], eventCuts, true);
      h.hadronCuts = cuts(definition["hadron_cuts"], hadronCuts, false);
      if (definition["kind"]) h.kind = definition["kind"].as<std::string>();
      if (h.kind != "multiplicity" && h.kind != "profile") throw std::runtime_error("kind must be multiplicity or profile");
      if (definition["normalization"]) h.normalization = definition["normalization"].as<std::string>();
      if (h.normalization != "per_dis" && h.normalization != "counts") throw std::runtime_error("normalization must be per_dis or counts");
      if (h.kind == "profile") {
        if (definition["normalization"]) throw std::runtime_error("Profiles are pooled hadron means; omit normalization");
        h.quantity = definition["quantity"].as<std::string>();
        if (h.quantity != "prod_time" && h.quantity != "form_time" && h.quantity != "formation_interval") variable(h.quantity);
      } else if (definition["quantity"]) throw std::runtime_error("quantity requires kind: profile");
      if (definition["species"]) {
        if (!definition["species"].IsSequence() || definition["species"].size() == 0) throw std::runtime_error("Histogram species must be a nonempty sequence");
        std::unordered_set<std::string> selected;
        for (const auto& key : definition["species"]) {
          const auto tag = key.as<std::string>();
          if (!species.count(tag) || !selected.insert(tag).second) throw std::runtime_error("Unknown or duplicate species: " + tag);
          h.species.push_back(species.at(tag));
        }
      } else for (const auto& item : species) h.species.push_back(item.second);
      const auto axes = definition["axes"];
      if (!axes.IsSequence() || axes.size() == 0) throw std::runtime_error("Histogram requires at least one axis");
      std::unordered_set<std::string> variables;
      std::size_t size = 1;
      for (const auto& node : axes) {
        auto a = axis(node);
        if (!variables.insert(a.variable).second) throw std::runtime_error("Duplicate axis variable");
        if (h.kind == "profile" && a.density) throw std::runtime_error("Profile axes cannot use density normalization");
        if (h.normalization == "counts" && a.density) throw std::runtime_error("Raw counts cannot use density normalization");
        h.strides.push_back(size);
        const auto extent = h.axes.empty() ? a.edges.size() + 1 : a.edges.size() - 1;
        if (size > 1000000 / extent) throw std::runtime_error("Histogram exceeds one million cells");
        size *= extent;
        h.axes.push_back(std::move(a));
      }
      allocatedCells += size * h.species.size();
      if (allocatedCells > 1000000) throw std::runtime_error("Analysis exceeds one million species/bin cells");
      h.cells.resize(h.species.size(), std::vector<Cell>(size));
      h.eventCounts.resize(h.species.size(), std::vector<double>(size));
      h.denominators.resize(size);
      histograms.push_back(std::move(h));
    }
  }

  void beginEvent(const MetaDIS& event, bool timeColumns) {
    meta = &event;
    if (targetA < 0) { targetA = event.A; targetZ = event.Z; }
    if (targetA != event.A || targetZ != event.Z) throw std::runtime_error("Analyze each target separately");
    weight = weighting == "metadata" ? event.weight : 1.0;
    if (weighting == "unit" && event.weight != 1.0) throw std::runtime_error("Non-unit event weight: select weighting: metadata");
    if (!std::isfinite(weight) || weight <= 0) throw std::runtime_error("Event weights must be finite and positive");
    for (auto& h : histograms) {
      h.accepted = passes(h.eventCuts);
      for (auto& counts : h.eventCounts) std::fill(counts.begin(), counts.end(), 0.0);
      std::fill(h.denominators.begin(), h.denominators.end(), false);
      if (!h.accepted) continue;
      if (!timeColumns && (h.quantity == "prod_time" || h.quantity == "form_time" || h.quantity == "formation_interval")) ++h.missingTimeEvents;
      for (std::size_t flat = 0; flat < h.denominators.size(); ++flat) {
        const auto index = h.indices(flat);
        bool matched = true;
        for (std::size_t i = 0; i < h.axes.size(); ++i) {
          if (!analysis_yaml::eventVariable(h.axes[i].variable)) continue;
          const double x = value(h.axes[i].variable);
          const auto bin = h.axes[i].bin(x);
          if (!std::isfinite(x) || bin != index[i] + (i == 0 ? 0 : 1)) { matched = false; break; }
        }
        h.denominators[flat] = matched;
      }
    }
  }

  void particle(const Particle& particle, const std::string& line,
                const std::unordered_map<std::string, std::size_t>& columns, bool timeColumns) {
    if (!std::isfinite(particle.p.E) || particle.p.E <= 0 || !std::isfinite(particle.p.px) ||
        !std::isfinite(particle.p.py) || !std::isfinite(particle.p.pz)) throw std::runtime_error("Invalid hadron four-momentum");
    for (auto& h : histograms) {
      if (!h.accepted || !passes(h.hadronCuts, &particle)) continue;
      std::vector<std::size_t> selected;
      for (std::size_t s = 0; s < h.species.size(); ++s) if (h.species[s].matches(particle)) selected.push_back(s);
      if (selected.empty()) continue;
      std::size_t flat = 0;
      bool inside = true;
      double xFirst = 0;
      for (std::size_t i = 0; i < h.axes.size(); ++i) {
        const double x = value(h.axes[i].variable, &particle);
        if (!std::isfinite(x)) { inside = false; break; }
        if (i == 0) xFirst = x;
        const auto bin = h.axes[i].bin(x);
        if (i > 0 && (bin == 0 || bin == h.axes[i].edges.size())) { inside = false; break; }
        flat += (i == 0 ? bin : bin - 1) * h.strides[i];
      }
      if (!inside) { ++h.outsideSlices; continue; }
      if (!h.denominators[flat]) throw std::runtime_error("Internal DIS bin mismatch");
      if (h.kind == "multiplicity") {
        for (auto s : selected) ++h.eventCounts[s][flat];
      } else {
        double y;
        if (h.quantity == "prod_time" || h.quantity == "form_time" || h.quantity == "formation_interval") {
          if (!timeColumns) continue;
          const auto fields = timeTokens(line);
          if (fields.size() != columns.size()) throw std::runtime_error("Time-profile particle column count differs from header");
          const int status = timeInteger(fields[columns.at("prod_time_status")]);
          if (status < 0 || status > 2) throw std::runtime_error("prod_time_status must be 0, 1 or 2");
          if (status != 1) { ++h.unavailableTimes; continue; }
          const double production = timeNumber(fields[columns.at("prod_time")]);
          const double formation = timeNumber(fields[columns.at("form_time")]);
          if (!std::isfinite(production) || !std::isfinite(formation)) throw std::runtime_error("Non-finite available coordinate time");
          y = h.quantity == "prod_time" ? production : h.quantity == "form_time" ? formation : formation - production;
        } else y = value(h.quantity, &particle);
        if (!std::isfinite(y)) throw std::runtime_error("Non-finite profile quantity: " + h.quantity);
        for (auto s : selected) {
          const std::array<long double, 7> increment = {weight, weight * weight, weight * xFirst,
              weight * xFirst * xFirst, weight * y, weight * y * y, 1};
          auto& profile = h.cells[s][flat].profile;
          for (std::size_t j = 0; j < profile.size(); ++j) profile[j] += increment[j];
        }
      }
    }
  }

  void endEvent() {
    for (auto& h : histograms) {
      if (!h.accepted) continue;
      for (std::size_t s = 0; s < h.species.size(); ++s) {
        for (std::size_t flat = 0; flat < h.cells[s].size(); ++flat) {
          if (!h.denominators[flat]) continue;
          auto& cell = h.cells[s][flat];
          const long double n = h.eventCounts[s][flat];
          cell.hadrons += weight * n;
          cell.squared += weight * weight * n * n;
          cell.weightedCount += weight * weight * n;
          cell.dis += weight;
          cell.disSquared += weight * weight;
          ++cell.events;
        }
      }
    }
  }

  void write(std::ostream& out) const {
    out << std::scientific << std::setprecision(17);
    out << "# ELECTRA configurable OSCAR analysis, schema 1\n# Configuration follows verbatim as YAML comments:\n";
    std::istringstream source(sourceText);
    std::string line;
    while (std::getline(source, line)) out << "# YAML | " << line << '\n';
    for (const auto& h : histograms) {
      const std::size_t extent = h.axes[0].edges.size() + 1;
      for (std::size_t slice = 0; slice < h.denominators.size() / extent; ++slice) {
        const auto index = h.indices(slice * extent);
        std::string base = "/" + name + "/" + h.name;
        std::ostringstream annotations;
        annotations << std::setprecision(17) << "Analysis: " << name << "\nSelection: YAML_V1_" << h.name
                    << "\nFrame: " << frameName(frame) << "\nWeighting: " << weighting
                    << "\nBeamEnergyGeV: " << beamEnergy << "\nBeamMassGeV: " << beamMass
                    << "\nBeamDirection: " << (beamDirection < 0 ? "-z" : "+z")
                    << "\nTargetZ: " << targetZ << "\nTargetA: " << targetA
                    << "\nAxis: " << h.axes[0].variable << "\nDimensions: " << h.axes.size()
                    << "\nOutsideSliceRange: " << h.outsideSlices
                    << "\nMissingTimeEvents: " << h.missingTimeEvents << "\nUnavailableTimes: " << h.unavailableTimes << '\n';
        for (std::size_t i = 1; i < h.axes.size(); ++i) {
          base += "/" + h.axes[i].variable + "_bin" + std::to_string(index[i]);
          annotations << "Slice" << i << ": " << h.axes[i].variable << ' ' << h.axes[i].edges[index[i]]
                      << ' ' << h.axes[i].edges[index[i] + 1] << '\n';
        }
        annotations << "DensityAxes:";
        for (const auto& axis : h.axes) if (axis.density) annotations << ' ' << axis.variable;
        annotations << '\n';
        for (std::size_t s = 0; s < h.species.size(); ++s) {
          Hist1D numerator(h.axes[0].edges), denominator(h.axes[0].edges), normalized(h.axes[0].edges), covariance(h.axes[0].edges);
          double sliceVolume = 1;
          for (std::size_t i = 1; i < h.axes.size(); ++i) if (h.axes[i].density) {
            sliceVolume *= h.axes[i].edges[index[i] + 1] - h.axes[i].edges[index[i]];
          }
          auto assign = [](Hist1D& hist, std::size_t bin, double sum, double squared, double entries) {
            if (bin == 0) { hist.underflow = sum; hist.underflow2 = squared; hist.underflowEntries = entries; }
            else if (bin == hist.edges.size()) { hist.overflow = sum; hist.overflow2 = squared; hist.overflowEntries = entries; }
            else {
              const auto j = bin - 1;
              const double center = 0.5 * (hist.edges[j] + hist.edges[j + 1]);
              hist.sumw[j] = sum; hist.sumw2[j] = squared; hist.entries[j] = entries;
              hist.sumwx[j] = sum * center; hist.sumwx2[j] = sum * center * center;
            }
          };
          for (std::size_t bin = 0; bin < extent; ++bin) {
            const auto& cell = h.cells[s][slice * extent + bin];
            assign(numerator, bin, cell.hadrons, cell.squared, cell.events);
            assign(denominator, bin, cell.dis, cell.disSquared, cell.events);
            assign(covariance, bin, cell.weightedCount, 0, cell.events);
            double volume = sliceVolume;
            if (h.axes[0].density && bin > 0 && bin + 1 < extent) volume *= h.axes[0].edges[bin] - h.axes[0].edges[bin - 1];
            const long double mean = cell.dis > 0 ? cell.hadrons / cell.dis : std::numeric_limits<long double>::quiet_NaN();
            const long double residual = cell.squared - 2 * mean * cell.weightedCount + mean * mean * cell.disSquared;
            const double variance = cell.events > 1 ? static_cast<double>(std::max(0.0L, residual) * cell.events /
                ((cell.events - 1) * cell.dis * cell.dis)) : std::numeric_limits<double>::quiet_NaN();
            assign(normalized, bin, static_cast<double>(mean) / volume, variance / (volume * volume), cell.events);
          }
          const auto suffix = "_" + h.species[s].name;
          if (s == 0) writeHist(out, denominator, base + "/DIS", 1.0, annotations.str() + "Normalization: raw_DIS\n");
          if (h.kind == "multiplicity") {
            writeHist(out, numerator, base + "/counts" + suffix, 1.0,
                      annotations.str() + "Normalization: raw_hadrons\nSecondMoment: EventHadronCountSquared\n");
            if (weighting == "metadata") writeHist(out, covariance, base + "/sum_w2_n" + suffix, 1.0,
                annotations.str() + "Statistic: SumEventWeightSquaredTimesHadronCount\n");
            if (h.normalization == "per_dis") writeHist(out, normalized, base + "/multiplicity" + suffix, 1.0,
                annotations.str() + "Normalization: per_DIS\nUncertainty: EventRatioStandardError\nEmptyBins: nan\n");
          } else {
            const auto path = base + "/mean_" + h.quantity + suffix;
            out << "BEGIN YODA_PROFILE1D_V2 " << path << "\nPath: " << path << "\nType: Profile1D\n"
                << annotations.str() << "Quantity: " << h.quantity << "\nWeightingDefinition: PooledPerHadron\n";
            if (h.quantity == "prod_time" || h.quantity == "form_time" || h.quantity == "formation_interval") {
              out << "TimeDefinition: StoredOSCARCoordinateTime\nTimeFrame: StoredOSCARFrame\nTimeUnit: fm/c\nProductionStatus: 1\n";
            }
            out << "---\n# ID ID sumw sumw2 sumwx sumwx2 sumwy sumwy2 numEntries\n";
            std::array<long double, 7> total{};
            for (std::size_t bin = 0; bin < extent; ++bin) for (std::size_t j = 0; j < total.size(); ++j) {
              total[j] += h.cells[s][slice * extent + bin].profile[j];
            }
            auto row = [&](const std::string& lo, const std::string& hi, const std::array<long double, 7>& moments) {
              out << lo << '\t' << hi;
              for (auto moment : moments) out << '\t' << moment;
              out << '\n';
            };
            row("Total", "Total", total);
            row("Underflow", "Underflow", h.cells[s][slice * extent].profile);
            row("Overflow", "Overflow", h.cells[s][slice * extent + extent - 1].profile);
            out << "# xlow xhigh sumw sumw2 sumwx sumwx2 sumwy sumwy2 numEntries\n";
            for (std::size_t bin = 1; bin + 1 < extent; ++bin) {
              out << h.axes[0].edges[bin - 1] << '\t' << h.axes[0].edges[bin];
              for (auto moment : h.cells[s][slice * extent + bin].profile) out << '\t' << moment;
              out << '\n';
            }
            out << "END YODA_PROFILE1D_V2\n\n";
          }
        }
      }
    }
  }
};

#else

class GenericAnalysis {
 public:
  explicit GenericAnalysis(const std::string&) {
    throw std::runtime_error("YAML analysis requires yaml-cpp; build with cmake -S utils -B build/analysis");
  }
  void beginEvent(const MetaDIS&, bool) {}
  void particle(const Particle&, const std::string&, const std::unordered_map<std::string, std::size_t>&, bool) {}
  void endEvent() {}
  void write(std::ostream&) const {}
};

#endif
