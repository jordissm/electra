# syntax=docker/dockerfile:1.4

ARG TARGET_ARCHITECTURE="x86-64"

ARG ROOT_VERSION="6.34.00"
ARG HEPMC_VERSION="3.2.6"
ARG CPPCHECK_VERSION="2.8"
ARG CPPLINT_VERSION="1.6.0"
ARG RIVET_VERSION="3.1.7"
ARG YODA_VERSION="1.9.7"
ARG FASTJET_VERSION="3.4.0"
ARG FJCONTRIB_VERSION="1.049"
ARG JULIA_VERSION="1.9.3"
ARG YQ_VERSION="4.40.3"

ARG PROJECT_DIR="/opt/electra"
ARG MNT_DIR="/workspace"
ARG OUTPUT_DIR="${MNT_DIR}/output"
ARG INPUT_DIR="${MNT_DIR}/input"
ARG HEPMC_INSTALL="${PROJECT_DIR}/hepmc3_install"

ARG PYTHONPATH=''
ARG MANPATH=''
ARG CMAKE_PREFIX_PATH=''
ARG JUPYTER_PATH=''
ARG JUPYTER_CONFIG_DIR=''
ARG TEXMFHOME=''
ARG HOMETEXMF=''
ARG TEXMFCNF=''
ARG TEXINPUTS=''
ARG LATEXINPUTS=''

# ARG CFLAGS="-O3 -march=${TARGET_ARCHITECTURE}"
# ARG CPPFLAGS="${CFLAGS} -std=c++17"
# ARG CXXFLAGS=${CPPFLAGS}



FROM ubuntu:22.04 AS setup

SHELL ["/bin/bash", "-c"]

ARG OPTFLAGS="-O3"
ARG ARCHFLAGS=""
ENV CFLAGS="${OPTFLAGS} ${ARCHFLAGS}" \
  CXXFLAGS="${OPTFLAGS} ${ARCHFLAGS} -std=c++17" \
  CPPFLAGS="${OPTFLAGS} ${ARCHFLAGS} -std=c++17"

LABEL installed.software.versions="\
  ROOT ${ROOT_VERSION}\
  | HepMC ${HEPMC_VERSION}\
  | Rivet ${RIVET_VERSION}\
  | Yoda ${YODA_VERSION}\
  | Fastjet ${FASTJET_VERSION}\
  | Fjcontrib ${FJCONTRIB_VERSION}\
  | Cppcheck ${CPPCHECK_VERSION}\
  | Cpplint ${CPPLINT_VERSION}\
  | Julia ${JULIA_VERSION}\
  | yq ${YQ_VERSION}"

LABEL org.opencontainers.image.title="electra"
LABEL org.opencontainers.image.authors="SURGE Collaboration"
LABEL org.opencontainers.image.source="https://github.com/jordissm/electra"
LABEL org.opencontainers.image.description="ELECTRA: eHIJING + SMASH cold nuclear medium framework"
LABEL org.opencontainers.image.licenses="GPL-3.0"

# =======================================================
#                   INSTALL DEPENDENCIES
# =======================================================

FROM setup AS dependencies
ARG PROJECT_DIR
ARG MNT_DIR
ARG OUTPUT_DIR
ARG INPUT_DIR
ARG DEBIAN_FRONTEND=noninteractive
ARG TARGETPLATFORM
ARG BUILDPLATFORM
ARG TARGETARCH
ARG TARGETOS
RUN --mount=type=cache,id=apt-cache-${TARGETPLATFORM},target=/var/cache/apt,sharing=locked \
  --mount=type=cache,id=apt-lists-${TARGETPLATFORM},target=/var/lib/apt/lists,sharing=locked \
  <<'EOF'
  # Installing dependencies
  set -euxo pipefail
  ln -sf /usr/share/zoneinfo/UTC /etc/localtime

  apt-get update
  apt-get -y upgrade
  apt-get -y install --no-install-recommends \
    aspell aspell-en autoconf automake autotools-dev bash bc build-essential \
    bzip2 ca-certificates clang-13 clang-format-13 clang-tidy-13 clang-tools-13 \
    cmake coreutils curl cython3 ddd debianutils diffutils doxygen \
    findutils gawk g++ gcc gcr gdb gfortran git gnupg gnupg-utils gnuplot \
    gnuplot-qt gperf graphviz grep gzip htop imagemagick ipython3 jupyter-notebook \
    less libc-bin libc-dev-bin libc-devtools libc++-13-dev libc++1-13 libc++abi-13-dev \
    libc++abi1-13 libclang-common-13-dev libclang-cpp13 libclang1-13 libeigen3-dev \
    libfreetype-dev libgif-dev libgmp-dev libgraphviz-dev libgsl-dev libjpeg-dev \
    libjpeg8-dev libllvm13 liblzma-dev libmpfr-dev libmpfrc++-dev libopenmpi-dev \
    libpcre3-dev libpcre++-dev libpng-dev libpng-tools libtbb-dev libssl-dev \
    libtool libx11-dev libxext-dev libxft-dev libxml2-dev libxpm-dev libxxhash-dev \
    libzstd-dev linux-libc-dev llvm-13 llvm-13-dev llvm-13-linker-tools llvm-13-runtime \
    llvm-13-tools locales locales-all lsb-base lsb-release lzma python3-args \
    python3-atomicwrites python3-colorama python3-cryptography python3-dateutil \
    python3-decorator python3-dev python3-distro python3-distutils python3-entrypoints \
    python3-future python3-importlib-metadata python3-ipython python3-ipython-genutils \
    python-is-python3 python3-mpi4py python3-numexpr python3-numpy python3-pandas \
    python3-patsy python3-pickleshare python3-pip python3-pkg-resources python3-prompt-toolkit \
    python3-psutil python3-ptyprocess python3-py python3-pytest python3-scipy python3-seaborn \
    python3-secretstorage python3-setuptools python3-simplejson python3-statsmodels \
    python3-systemd python3-tables python3-urllib3 python3-yaml python3-zipp qiv rsync screen \
    sed sensible-utils sqlite3 tar tree unzip util-linux valgrind vim wget \
    xxhash xz-utils zip
    # evince qiv zenity x11-common x11-xkb-utils x11-xserver-utils xauth xdot xfonts-base \
    # xfonts-encodings xfonts-utils xkb-data xorg-sgml-doctools xserver-common \
    # xserver-xorg xserver-xorg-core xserver-xorg-input-all xserver-xorg-input-libinput \
    # xserver-xorg-legacy x11vnc xvfb

  rm -rf /var/lib/apt/lists/*
EOF

RUN <<EOF
  set -eux
  mv /usr/bin/screen /usr/bin/screen.exe
  cat > /usr/bin/screen <<'INTERNAL_EOF'
    printf '%s\n'\
          'Executing screen wrapper script around original program /usr/bin/screen.exe'\
          'We try to set the environment variable SCREENDIR to ${HOME}/.screen_dir,'\
          'if this directory is not accessible, please, manually set SCREENDIR to another directory'\
          'before launching /usr/bin/screen.exe'
    sleep 3
    export SCREENDIR="${HOME}/.screen_dir"
    mkdir -p "${SCREENDIR}"
    chmod 700 "${SCREENDIR}"
    /usr/bin/screen.exe "$@"
INTERNAL_EOF
  chmod 755 /usr/bin/screen
EOF

ENV LD_LIBRARY_PATH=''

WORKDIR ${MNT_DIR}
RUN mkdir -p "${PROJECT_DIR}" "${MNT_DIR}" "${OUTPUT_DIR}" "${INPUT_DIR}"

# =======================================================
#                     INSTALL HEPMC3
# =======================================================

FROM dependencies AS hepmc3-install
ARG PROJECT_DIR
ARG HEPMC_INSTALL
ARG HEPMC_VERSION

RUN <<EOF
  # Installing HepMC3
  set -euxo pipefail
  cd ${PROJECT_DIR}
  wget https://hepmc.web.cern.ch/hepmc/releases/HepMC3-${HEPMC_VERSION}.tar.gz
  tar xf HepMC3-${HEPMC_VERSION}.tar.gz
  mkdir -p HepMC3_build
  cd HepMC3_build
  cmake -DHEPMC3_ENABLE_ROOTIO:BOOL=OFF \
        -DHEPMC3_ENABLE_TEST:BOOL=OFF \
        -DHEPMC3_INSTALL_INTERFACES:BOOL=ON \
        -DHEPMC3_ENABLE_PYTHON:BOOL=OFF \
        -DHEPMC3_BUILD_STATIC_LIBS:BOOL=OFF \
        -DHEPMC3_BUILD_DOCS:BOOL=OFF \
        -DCMAKE_INSTALL_PREFIX=../hepmc3_install ../HepMC3-${HEPMC_VERSION}
  make -j$(nproc)
  make install
  printf "${HEPMC_INSTALL}/lib\n" >> /etc/ld.so.conf
  ldconfig
EOF

ENV PATH=${HEPMC_INSTALL}/bin:${PATH}
ENV ROOT_INCLUDE_PATH=${PROJECT_DIR}/hepmc3_install/include/

# =======================================================
#                    INSTALL GITSTATS
# =======================================================

FROM hepmc3-install AS gitstats-install
ARG PROJECT_DIR

RUN <<EOF
  # Installing gitstats
  set -euxo pipefail
  cd ${PROJECT_DIR}
  git clone https://github.com/hoxu/gitstats.git
  cd gitstats
  make install
EOF

# =======================================================
#              INSTALL CPPCHECK AND CPPLINT
# =======================================================

FROM gitstats-install AS cppcheck-cpplint-install
ARG PROJECT_DIR
ARG CPPCHECK_VERSION
ARG CPPLINT_VERSION

RUN <<EOF
  # Installing cpp-check and cpp-lint
  set -euxo pipefail
  cd ${PROJECT_DIR}
  wget https://github.com/danmar/cppcheck/archive/${CPPCHECK_VERSION}.tar.gz
  tar xf ${CPPCHECK_VERSION}.tar.gz
  cd cppcheck-${CPPCHECK_VERSION}
  mkdir -p build
  cd build
  cmake ..
  cmake --build .
  cd ${PROJECT_DIR}

  wget https://github.com/cpplint/cpplint/archive/refs/tags/${CPPLINT_VERSION}.tar.gz
  tar xf ${CPPLINT_VERSION}.tar.gz

  mkdir -p ${PROJECT_DIR}/auxiliary_progs/
  mv cppcheck-${CPPCHECK_VERSION}/build/bin/cppcheck cpplint-${CPPLINT_VERSION}/cpplint.py ${PROJECT_DIR}/auxiliary_progs/
  chmod +x ${PROJECT_DIR}/auxiliary_progs/*
EOF

ENV PATH=${PATH}:${PROJECT_DIR}/auxiliary_progs

# =======================================================
#                      INSTALL RIVET
# =======================================================

FROM cppcheck-cpplint-install AS rivet-install
ARG PROJECT_DIR
ARG HEPMC_INSTALL
ARG RIVET_VERSION
ARG YODA_VERSION
ARG FASTJET_VERSION
ARG FJCONTRIB_VERSION
ARG RIVET_INSTALL_PREFIX="${PROJECT_DIR}/Rivet_install"
ARG RIVET_BUILD_PREFIX="${PROJECT_DIR}/rivet_build"
ARG FASTJET_PATH=${RIVET_INSTALL_PREFIX}
ARG YODA_PATH=${RIVET_INSTALL_PREFIX}

RUN <<EOF
  # Installing Rivet
  set -euxo pipefail
  printf 'Preparing Rivet installation\n'
  mkdir -p ${RIVET_INSTALL_PREFIX}/etc/bash_completion.d \
           ${RIVET_INSTALL_PREFIX}/lib
  ln -s lib ${RIVET_INSTALL_PREFIX}/lib64
  mkdir -p ${RIVET_BUILD_PREFIX}

  printf 'Installing Fastjet\n'
  cd ${RIVET_BUILD_PREFIX}
  wget --no-check-certificate --no-verbose \
       http://www.fastjet.fr/repo/fastjet-${FASTJET_VERSION}.tar.gz -O- | tar --no-same-owner -xz
  cd fastjet-${FASTJET_VERSION}
  ./configure --prefix=${RIVET_INSTALL_PREFIX} --enable-shared --disable-auto-ptr --enable-allcxxplugins
  make -j$(nproc)
  make install

  printf 'Installing Fastjet-contrib\n'
  cd ${RIVET_BUILD_PREFIX}
  wget --no-check-certificate --no-verbose \
       http://cedar-tools.web.cern.ch/downloads/fjcontrib-${FJCONTRIB_VERSION}.tar.gz -O- | tar --no-same-owner -xz
  cd fjcontrib-${FJCONTRIB_VERSION}
  ./configure --fastjet-config=${FASTJET_PATH}/bin/fastjet-config CXXFLAGS=-fPIC
  sed -i.bak -e 's/#include <array>/#include <array>\n#include <limits>/' LundPlane/EEHelpers.hh
  make -j1 fragile-shared-install
  make install

  printf 'Installing Yoda\n'
  cd ${RIVET_BUILD_PREFIX}
  wget --no-check-certificate --no-verbose \
       http://cedar-tools.web.cern.ch/downloads/YODA-${YODA_VERSION}.tar.gz -O- | tar --no-same-owner -xz
  cd YODA-${YODA_VERSION}
  ./configure --prefix=${YODA_PATH}
  make -j$(nproc)
  make install
  cp yodaenv.sh ${YODA_PATH}/yodaenv.sh

  printf 'Installing Rivet\n'
  cd ${RIVET_BUILD_PREFIX}
  wget --no-check-certificate --no-verbose \
       http://cedar-tools.web.cern.ch/downloads/Rivet-${RIVET_VERSION}.tar.gz -O- | tar --no-same-owner -xz
  cd Rivet-${RIVET_VERSION}
  ./configure --prefix=${RIVET_INSTALL_PREFIX} \
              --with-yoda=${YODA_PATH} \
              --with-hepmc3=${HEPMC_INSTALL} \
              --with-fastjet=${FASTJET_PATH}
  make -j$(nproc)
  make install
  cp rivetenv.sh ${RIVET_INSTALL_PREFIX}
  printf "${RIVET_INSTALL_PREFIX}/lib\n" >> /etc/ld.so.conf
  ldconfig
EOF

ENV PYTHON=/usr/bin/python3
ENV PATH=${RIVET_INSTALL_PREFIX}/bin:${PATH}
ENV LD_LIBRARY_PATH="${RIVET_INSTALL_PREFIX}/lib:${RIVET_INSTALL_PREFIX}/lib64:${LD_LIBRARY_PATH}"
ENV PYTHONPATH="${RIVET_INSTALL_PREFIX}/lib/python3.10/site-packages:${PYTHONPATH}"
ENV TEXMFHOME="${RIVET_INSTALL_PREFIX}/share/Rivet/texmf:${TEXMFHOME}"
ENV HOMETEXMF="${RIVET_INSTALL_PREFIX}/share/Rivet/texmf:${HOMETEXMF}"
ENV TEXMFCNF="${RIVET_INSTALL_PREFIX}/share/Rivet/texmf/cnf:${TEXMFCNF}"
ENV TEXINPUTS="${RIVET_INSTALL_PREFIX}/share/Rivet/texmf/tex:${TEXINPUTS}"
ENV LATEXINPUTS="${RIVET_INSTALL_PREFIX}/share/Rivet/texmf/tex:${LATEXINPUTS}"

# =======================================================
#                      INSTALL YQ
# =======================================================

FROM rivet-install AS yq-install
ARG PROJECT_DIR
ARG YQ_VERSION
ARG TARGETARCH

RUN <<EOF
  # Installing yq
  set -euxo pipefail
  case "${TARGETARCH}" in
    amd64) YQ_BINARY="yq_linux_amd64" ;;
    arm64) YQ_BINARY="yq_linux_arm64" ;;
    *) echo "Unsupported TARGETARCH=${TARGETARCH}" ; exit 1 ;;
  esac
  cd ${PROJECT_DIR}
  wget https://github.com/mikefarah/yq/releases/download/v${YQ_VERSION}/${YQ_BINARY} -O /usr/bin/yq
  chmod +x /usr/bin/yq
EOF

# =======================================================
#                    INSTALL PYTHIA8
# =======================================================

FROM yq-install AS pythia-install
ARG PROJECT_DIR

RUN <<EOF
  # Installing pythia
  set -euxo pipefail
  cd ${PROJECT_DIR}
  wget https://pythia.org/download/pythia83/pythia8316.tgz
  tar -xf pythia8316.tgz && rm pythia8316.tgz
  cd pythia8316
  ./configure --cxx-common='-std=c++17 -O3 -fPIC'
  make -j$(nproc)
EOF


# =======================================================
#                     INSTALL SMASH
# =======================================================

FROM pythia-install AS smash-build
ARG PROJECT_DIR
ARG HEPMC_INSTALL

RUN <<EOF
  # Installing smash
  # .
  # .
  set -euxo pipefail
  mkdir -p ${PROJECT_DIR}/smash_bin
  cd ${PROJECT_DIR}
  git clone https://github.com/jordissm/smash.git
  mkdir -p smash/build
  cd smash/build
  set +e
  cmake -DPythia_CONFIG_EXECUTABLE=${PROJECT_DIR}/pythia8316/bin/pythia8-config \
        -DCMAKE_INSTALL_PREFIX=${HEPMC_INSTALL} ..
  if [[ $? -ne 0 ]]; then
    echo "Error: cmake SMASH build configuration failed!"
    exit 1
  fi
  cd ${PROJECT_DIR}/smash/build || exit 1
  make smash -j$(nproc)
  if [[ $? -ne 0 ]]; then
    echo "Error: make SMASH compilation failed!"
  fi
  if [[ -f ${PROJECT_DIR}/smash/build/smash ]]; then
    cp ${PROJECT_DIR}/smash/build/smash ${PROJECT_DIR}/smash_bin/
    cp ${PROJECT_DIR}/smash/build/config.yaml ${PROJECT_DIR}/smash_bin/
  else
    echo "SMASH executable not found! Something went wrong compiling SMASH!"
    exit 1
  fi
EOF

# =======================================================
#                    INSTALL EHIJING
# =======================================================
FROM smash-build AS ehijing-install
ARG PROJECT_DIR

RUN <<EOF
  # Installing ehijing
  # .
  # .
  set -euxo pipefail
  mkdir -p ${PROJECT_DIR}/ehijing_bin
  cd ${PROJECT_DIR}
  git clone https://github.com/jordissm/ehijing.git
  cd ehijing/external/pythia8
  ./configure --cxx-common='-std=c++17 -O3 -fPIC'
  make -j$(nproc)
  mkdir -p ${PROJECT_DIR}/ehijing/build
  cd ${PROJECT_DIR}/ehijing/build
  cmake -DPYTHIA8_INCLUDE_DIR=${PROJECT_DIR}/ehijing/external/pythia8/include/ \
        -DPYTHIA8_LIBRARY=${PROJECT_DIR}/ehijing/external/pythia8/lib/libpythia8.a ..
  make ehijing -j$(nproc)
  if [[ $? -ne 0 ]]; then
    echo "Error: 'make ehijing -j$(nproc)' compilation failed!"
  fi
  if [[ -f ${PROJECT_DIR}/ehijing/build/ehijing ]]; then
    cp ${PROJECT_DIR}/ehijing/build/ehijing ${PROJECT_DIR}/ehijing_bin/
    cp -r ${PROJECT_DIR}/ehijing/config/ ${PROJECT_DIR}/ehijing_bin/
    cp -r ${PROJECT_DIR}/ehijing/scripts/ ${PROJECT_DIR}/ehijing_bin/
  else
    echo "ehijing executable not found! Something went wrong compiling ehijing!"
    exit 1
  fi
EOF


# =======================================================
#                 CLEANUP AND FINAL IMAGE
# =======================================================

FROM ehijing-install AS final-image
ARG PROJECT_DIR
ARG MNT_DIR
ARG OUTPUT_DIR
ARG INPUT_DIR
ARG HEPMC_VERSION
ARG CPPCHECK_VERSION
ARG CPPLINT_VERSION
ARG ROOT_VERSION
ARG RIVET_BUILD_PREFIX

RUN <<EOF
  # Finalizing and producing final image
  set -euxo pipefail
  cd ${PROJECT_DIR}
  rm -rf HepMC3-${HEPMC_VERSION} \
         HepMC3-${HEPMC_VERSION}.tar.gz \
         HepMC3_build \
         gitstats \
         cppcheck-${CPPCHECK_VERSION} \
         ${CPPCHECK_VERSION}.tar.gz \
         cpplint-${CPPLINT_VERSION} \
         ${CPPLINT_VERSION}.tar.gz \
         ${RIVET_BUILD_PREFIX} \
         /var/cache/apt/archives/*.deb
  sed -i -e "/ghostscript/d" -e "/PS/d" -e "/PS2/d" -e "/PS3/d" \
         -e "/EPS/d" -e "/PDF/d" -e "/XPS/d" /etc/ImageMagick-6/policy.xml
  ln -s /usr/bin/clang-format-13 /usr/bin/clang-format
  ln -s /usr/bin/clang-tidy-13 /usr/bin/clang-tidy
  pip install cmakelang

  install -d /usr/local/bin
  install -m 0755 ${PROJECT_DIR}/ehijing_bin/ehijing /usr/local/bin/ehijing
  install -m 0755 ${PROJECT_DIR}/smash_bin/smash /usr/local/bin/smash
EOF

# PATCH: install the electra python package into the image (late for caching)
# Assumes build context is the repo root containing pyproject.toml + python/electra/*
COPY pyproject.toml README.md ${PROJECT_DIR}/electra_src/
COPY python/                  ${PROJECT_DIR}/electra_src/python/
COPY rivet-analyses/          ${PROJECT_DIR}/share/rivet-analyses/
COPY utils/                   ${PROJECT_DIR}/share/utils/
COPY input/                   ${PROJECT_DIR}/share/input-defaults/
COPY slurm-scripts/           ${PROJECT_DIR}/share/slurm-scripts/

RUN <<'EOF'
  set -euxo pipefail

  # Make packaging toolchain modern enough for PEP 621 reliably
  python3 -m pip install --no-cache-dir --upgrade pip setuptools wheel

  # Now install electra
  python3 -m pip install --no-cache-dir "${PROJECT_DIR}"/electra_src

  # Validate
  python3 -m pip show electra
  command -v electra
  electra --help >/dev/null
EOF

ENV SMASH_DIR=${PROJECT_DIR}/smash
ENV SMASH_BUILD_DIR=${PROJECT_DIR}/smash_bin
ENV LC_ALL=en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US.UTF-8
ENV PROMPT_CONTAINER_NAME='electra'

RUN <<'EOF'
  set -eux
  COMMON_PS1='${PROMPT_CONTAINER_NAME:-SMASH} - \D{%d.%m.%y %H:%M:%S} \001\033[1;94m\002\w\001\033[0m\002 \$ '
  printf "\n\nexport PS1='🔬 %s'\n" "${COMMON_PS1}" >> ~/.bashrc
  mkdir -p /.singularity.d/env
  CUSTOM_ENV=/.singularity.d/env/99-zz_custom_env.sh
  printf "%s\n\n\nexport PS1='🔬 %s'\n\n"\
         '#!/bin/bash'\
         "${COMMON_PS1}" > "${CUSTOM_ENV}"
  chmod 755 "${CUSTOM_ENV}"
EOF

RUN <<'EOF' cat > /usr/local/bin/entrypoint.sh
#!/usr/bin/env bash
set -e

cat <<'BANNER'
=============================================================================
          ,;                    ,;      .,                                  
        f#i            i      f#i      ,Wt          j.                      
      .E#t            LE    .E#t      i#D. GEEEEEEELEW,                   ..
     i#W,            L#E   i#W,      f#f   ,;;L#K;;.E##j                 ;W,
    L#D.            G#W.  L#D.     .D#i       t#E   E###D.              j##,
  :K#Wfff;         D#K. :K#Wfff;  :KW,        t#E   E#jG#W;            G###,
  i##WLLLLt       E#K.  i##WLLLLt t#f         t#E   E#t t##f         :E####,
   .E#L         .E#E.    .E#L      ;#G        t#E   E#t  :K#E:      ;W#DG##,
     f#E:      .K#E        f#E:     :KE.      t#E   E#KDDDD###i    j###DW##,
      ,WW;    .K#D          ,WW;     .DW:     t#E   E#f,t#Wi,,,   G##i,,G##,
       .D#;  .W#G            .D#;      L#,    t#E   E#t  ;#W:   :K#K:   L##,
         tt :W##########Wt     tt       jt     fE   DWi   ,KK: ;##D.    L##,
            :,,,,,,,,,,,,,.                     :              ,,,      .,, 
=============================================================================                                                             
BANNER

echo "Started: $(date)"
echo "User: $(whoami)"

exec "$@"
EOF

RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["/bin/bash"]
