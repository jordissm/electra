# syntax=docker/dockerfile:1.4

# Set the proper general cpu family architecture flag.
# Please, for more information refer to the documention of your compiler.

ARG TARGET_ARCHITECTURE="x86-64"

# Declare all together the versions of the going to be installed codebases

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
ARG MNT_DIR="${PROJECT_DIR}/mnt"
ARG HEPMC_INSTALL="${PROJECT_DIR}/hepmc3_install"

# Set PATH-like environment variables to comply with Docker suggestion to always define these
# before using them (otherwise an UndefinedVar warning is given by Docker at build time). Note
# that the base image already define LD_LIBRARY_PATH and we clearly do not want to reset this one.

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

# Set cpu architecture flags for compilation
# ARG sets these flags as temporary environment variables that are used by cmake and by other tools

ARG CFLAGS="-O3 -march=${TARGET_ARCHITECTURE}"
ARG CPPFLAGS="${CFLAGS} -std=c++17"
ARG CXXFLAGS=${CPPFLAGS}


# Import the base smash Docker container image.
# Adjust the address as needed. In particular, be sure to use a base image compatible with your cpu.
# The official Docker images are prepared for a generic Intel/AMD x86-64 cpu.

FROM ubuntu:22.04 AS setup

# Set bash as the default shell in this Dockerfile

SHELL ["/bin/bash", "-c"]

# Set a label to keep track of all versions (these can be viewed with "docker inspect")
# Separate them with a '|' to potentially make them easily parsable

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

# Add some info about authors and contents using the rules o the OCI Image Format Specification
# https://github.com/opencontainers/image-spec/blob/main/annotations.md#pre-defined-annotation-keys

LABEL org.opencontainers.image.title="electra"
LABEL org.opencontainers.image.authors="SURGE Collaboration"
LABEL org.opencontainers.image.description="\
  eHIJING + SMASH + HepMC3 + Rivet + tools"



# =======================================================
# =======================================================
#                   INSTALL DEPENDENCIES
# =======================================================
# =======================================================

# Install dependencies
FROM setup AS dependencies
ARG PROJECT_DIR
ARG MNT_DIR
ARG DEBIAN_FRONTEND=noninteractive
RUN --mount=type=cache,target=/var/cache/apt <<'EOF'
  # apt-get update/upgrade/install
  set -euxo pipefail
  ln -sf /usr/share/zoneinfo/UTC /etc/localtime

  echo "==> Updating apt package lists"
  apt-get update

  echo "==> Upgrading base system"
  apt-get -y upgrade

  echo "==> Installing required packages"
  apt-get -y install --no-install-recommends \
    aspell  \
    aspell-en  \
    autoconf  \
    automake  \
    autotools-dev  \
    bash \
    bc \
    build-essential  \
    bzip2  \
    ca-certificates  \
    clang-13 \
    clang-format-13 \
    clang-tidy-13 \
    clang-tools-13 \
    cmake  \
    coreutils  \
    curl \
    cython3 \
    ddd  \
    debianutils  \
    diffutils  \
    doxygen  \
    evince  \
    findutils  \
    gawk  \
    g++ \
    gcc  \
    gcr  \
    gdb  \
    gfortran  \
    git  \
    gnupg  \
    gnupg-utils  \
    gnuplot  \
    gnuplot-qt  \
    gperf  \
    graphviz \
    grep  \
    gzip  \
    imagemagick \
    ipython3  \
    jupyter-notebook \
    libc-bin  \
    libc-dev-bin  \
    libc-devtools \
    libc++-13-dev \
    libc++1-13 \
    libc++abi-13-dev \
    libc++abi1-13 \
    libclang-common-13-dev \
    libclang-cpp13 \
    libclang1-13 \
    libeigen3-dev \
    libfreetype-dev \
    libgif-dev  \
    libgmp-dev  \
    libgraphviz-dev  \
    libgsl-dev  \
    libjpeg-dev  \
    libjpeg8-dev  \
    libllvm13 \
    liblzma-dev  \
    libmpfr-dev  \
    libmpfrc++-dev  \
    libopenmpi-dev \
    libpcre3-dev \
    libpcre++-dev  \
    libpng-dev  \
    libpng-tools  \
    libtbb-dev \
    libssl-dev  \
    libtool  \
    libx11-dev  \
    libxext-dev \
    libxft-dev \
    libxml2-dev \
    libxpm-dev \
    libxxhash-dev \
    libzstd-dev \
    linux-libc-dev \
    llvm-13 \
    llvm-13-dev \
    llvm-13-linker-tools \
    llvm-13-runtime \
    llvm-13-tools \
    locales \
    locales-all \
    lsb-base  \
    lsb-release  \
    lzma  \
    python3-args  \
    python3-atomicwrites  \
    python3-colorama  \
    python3-cryptography  \
    python3-dateutil  \
    python3-decorator  \
    python3-dev  \
    python3-distro  \
    python3-distutils  \
    python3-entrypoints  \
    python3-future  \
    python3-importlib-metadata  \
    python3-ipython  \
    python3-ipython-genutils  \
    python-is-python3  \
    python3-mpi4py \
    python3-numexpr  \
    python3-numpy  \
    python3-pandas  \
    python3-patsy  \
    python3-pickleshare  \
    python3-pip \
    python3-pkg-resources  \
    python3-prompt-toolkit  \
    python3-psutil  \
    python3-ptyprocess  \
    python3-py  \
    python3-pytest  \
    python3-scipy  \
    python3-seaborn  \
    python3-secretstorage  \
    python3-setuptools  \
    python3-simplejson  \
    python3-statsmodels  \
    python3-systemd  \
    python3-tables  \
    python3-urllib3  \
    python3-yaml  \
    python3-zipp  \
    qiv  \
    rsync  \
    screen  \
    sed  \
    sensible-utils  \
    sqlite3  \
    tar  \
    tree \
    unzip  \
    util-linux  \
    valgrind  \
    vim  \
    wget \
    x11-common  \
    x11-xkb-utils  \
    x11-xserver-utils  \
    xauth  \
    xdot \
    xfonts-base  \
    xfonts-encodings  \
    xfonts-utils  \
    xkb-data  \
    xml-core  \
    xorg-sgml-doctools  \
    xserver-common  \
    xserver-xorg  \
    xserver-xorg-core  \
    xserver-xorg-input-all  \
    xserver-xorg-input-libinput  \
    xserver-xorg-legacy  \
    xxhash \
    xz-utils  \
    zenity  \
    zip
echo "==> Cleaning up apt cache"
rm -rf /var/lib/apt/lists/*
EOF

# Build wrapper script around screen executable to make it usable from within the container
# (it needs write access to SCREENDIR folder). Note that quoting the sentinel word in the
# here-doc construct prevents to expand any ${...} inside (which is what we want here).

RUN <<EOF
  # Build wrapper script around screen executable
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

# Set LD_LIBRARY_PATH environment variable to comply with Docker suggestion to always define
# variables before using them (otherwise an UndefinedVar warning is given by Docker at build time).
# Note that the base Ubuntu image already define PATH and we clearly do not want to reset this one.

ENV LD_LIBRARY_PATH=''

# Create main project directory

WORKDIR ${PROJECT_DIR}
WORKDIR ${MNT_DIR}
RUN mkdir -p "${PROJECT_DIR}" "${MNT_DIR}" /workspace

# =======================================================
# =======================================================
#                      INSTALL ROOT
# =======================================================
# =======================================================

# Install ROOT
# FROM dependencies AS root-install
# RUN <<EOF
#   set -euxo pipefail
#   echo "==> Downloading ROOT ${ROOT_VERSION}"
#   cd ${PROJECT_DIR}
#   wget https://root.cern/download/root_v${ROOT_VERSION}.source.tar.gz
#   tar xf root_v${ROOT_VERSION}.source.tar.gz
#   mv root-${ROOT_VERSION} root_src
#   mkdir -p root_install root_build
#   cd root_build
#   echo "==> Configuring ROOT"
#   cmake -DCMAKE_INSTALL_PREFIX=../root_install ../root_src \
#         -Dxrootd=OFF \
#         -Dbuiltin_tbb=OFF \
#         -Ddavix=OFF
#   echo "==> Building and installing ROOT"
#   cmake --build . --target install -j$(nproc)
#   printf '${PROJECT_DIR}/root_install/lib\n' >> /etc/ld.so.conf
#   ldconfig
# EOF

# ENV ROOTSYS=${PROJECT_DIR}/root_install
# ENV PATH=${ROOTSYS}/bin:${PATH}
# ENV LD_LIBRARY_PATH=${ROOTSYS}/lib:${LD_LIBRARY_PATH}
# ENV SHLIB_PATH=${ROOTSYS}/lib
# ENV LIBPATH=${ROOTSYS}/lib
# ENV PYTHONPATH=${ROOTSYS}/lib:${PYTHONPATH}
# ENV MANPATH=${ROOTSYS}/man:${MANPATH}
# ENV CMAKE_PREFIX_PATH=${ROOTSYS}:${CMAKE_PREFIX_PATH}
# ENV JUPYTER_PATH=${ROOTSYS}/etc/notebook:${JUPYTER_PATH}
# ENV JUPYTER_CONFIG_DIR=${ROOTSYS}/etc/notebook:${JUPYTER_CONFIG_DIR}
# ENV CLING_STANDARD_PCH=none


# =======================================================
# =======================================================
#                     INSTALL HEPMC3
# =======================================================
# =======================================================

# Install HepMC3
FROM dependencies AS hepmc3-install
ARG PROJECT_DIR
ARG HEPMC_INSTALL
ARG HEPMC_VERSION

RUN <<EOF
  # Download and build HepMC3
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
# This is needed to make ROOT correctly find HEPMC files
ENV ROOT_INCLUDE_PATH=${PROJECT_DIR}/hepmc3_install/include/

# =======================================================
# =======================================================
#                    INSTALL GITSTATS
# =======================================================
# =======================================================

# Install gitstats
FROM hepmc3-install AS gitstats-install
ARG PROJECT_DIR

RUN <<EOF
  # Download and build gitstats
  set -euxo pipefail
  cd ${PROJECT_DIR}
  git clone https://github.com/hoxu/gitstats.git
  cd gitstats
  make install
EOF

# =======================================================
# =======================================================
#              INSTALL CPPCHECK AND CPPLINT
# =======================================================
# =======================================================

# Install cppcheck and cpplint
FROM gitstats-install AS cppcheck-cpplint-install
ARG PROJECT_DIR
ARG CPPCHECK_VERSION
ARG CPPLINT_VERSION

RUN <<EOF
  # Download and build Cppcheck and Cpplint
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
# =======================================================
#                      INSTALL RIVET
# =======================================================
# =======================================================

# (the versions of the dependent libraries listed at the top of this file
# are chosen according to the bootstrap script downloadable from the Rivet website)

# Install Rivet
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
  # Download and build Rivet and its dependencies: Fastjet, Fastjet-contrib and Yoda
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
# The python version must be updated together with the underlying linux distribution.
# Unfortunately something like $(python3 -V | cut -d " " -f 2) does not work in an ENV statement.
ENV PYTHONPATH="${RIVET_INSTALL_PREFIX}/lib/python3.10/site-packages:${PYTHONPATH}"
# ENV PYTHONPATH="${RIVET_INSTALL_PREFIX}/lib/python3.8.10/site-packages:${PYTHONPATH}"
ENV TEXMFHOME="${RIVET_INSTALL_PREFIX}/share/Rivet/texmf:${TEXMFHOME}"
ENV HOMETEXMF="${RIVET_INSTALL_PREFIX}/share/Rivet/texmf:${HOMETEXMF}"
ENV TEXMFCNF="${RIVET_INSTALL_PREFIX}/share/Rivet/texmf/cnf:${TEXMFCNF}"
ENV TEXINPUTS="${RIVET_INSTALL_PREFIX}/share/Rivet/texmf/tex:${TEXINPUTS}"
ENV LATEXINPUTS="${RIVET_INSTALL_PREFIX}/share/Rivet/texmf/tex:${LATEXINPUTS}"


# =======================================================
# =======================================================
#                     INSTALL JULIA
# =======================================================
# =======================================================

# Install julia
# FROM rivet-install AS julia-install
# ARG JULIA_PATH=/opt/julia-${JULIA_VERSION}
# RUN <<EOF
#   set -euxo pipefail
#   cd /opt
#   wget https://github.com/JuliaLang/julia/releases/download/v${JULIA_VERSION}/julia-${JULIA_VERSION}.tar.gz
#   tar xf julia-${JULIA_VERSION}.tar.gz
#   cd julia-${JULIA_VERSION}
#   make -j$(nproc)
# EOF

# ENV PATH=${JULIA_PATH}:${PATH}


# =======================================================
# =======================================================
#                      INSTALL YQ
# =======================================================
# =======================================================

# Install yq
FROM rivet-install AS yq-install
ARG YQ_VERSION
ARG YQ_BINARY=yq_linux_amd64

RUN <<EOF
  # Download yq
  set -euxo pipefail
  cd /opt
  wget https://github.com/mikefarah/yq/releases/download/v${YQ_VERSION}/${YQ_BINARY} -O /usr/bin/yq
  chmod +x /usr/bin/yq
EOF

# =======================================================
# =======================================================
#                   INSTALL EHIJING
# =======================================================
# =======================================================



# =======================================================
# =======================================================
#                   INSTALL PYTHIA8
# =======================================================
# =======================================================
FROM yq-install AS pythia-install
ARG PROJECT_DIR

RUN <<EOF
  # Download and build Pythia8
  set -euxo pipefail
  cd ${PROJECT_DIR}
  wget https://pythia.org/download/pythia83/pythia8316.tgz
  tar -xf pythia8316.tgz && rm pythia8316.tgz
  cd pythia8316
  ./configure --cxx-common='-std=c++11 -march=native -O3 -fPIC'
  make -j$(nproc)
EOF

# =======================================================
# =======================================================
#                     INSTALL SMASH
# =======================================================
# =======================================================

# Install SMASH
FROM pythia-install AS smash-build
ARG PROJECT_DIR
ARG MNT_DIR
ARG HEPMC_INSTALL

RUN <<EOF
  # Download and build SMASH
  set -euxo pipefail
  mkdir -p ${MNT_DIR}/smash_bin
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
    cp ${PROJECT_DIR}/smash/build/smash ${MNT_DIR}/smash_bin/
    cp ${PROJECT_DIR}/smash/build/config.yaml ${MNT_DIR}/smash_bin/
  else
    echo "SMASH executable not found! Something went wrong compiling SMASH!"
    exit 1
  fi
EOF



# Miscellaneous:
#  1. Remove most of the sources
#  2. Allow Imagemagick to process PS, EPS and PDF files in case the user needs to use `convert` inside the container
#  3. Set a symbolic link to clang-format-13 and clang-tidy-13 to make them usable from the SMASH formatting script
#  4. Install cmake-format

# Cleanup and final adjustments
FROM smash-build AS final-image
ARG PROJECT_DIR
ARG MNT_DIR
ARG HEPMC_VERSION
ARG CPPCHECK_VERSION
ARG CPPLINT_VERSION
ARG ROOT_VERSION
ARG RIVET_BUILD_PREFIX

RUN <<EOF
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
         root_v${ROOT_VERSION}.source.tar.gz \
         root_build \
         root_src \
         ${RIVET_BUILD_PREFIX} \
         /var/cache/apt/archives/*.deb
  sed -i -e "/ghostscript/d" -e "/PS/d" -e "/PS2/d" -e "/PS3/d" \
         -e "/EPS/d" -e "/PDF/d" -e "/XPS/d" /etc/ImageMagick-6/policy.xml
  ln -s /usr/bin/clang-format-13 /usr/bin/clang-format
  ln -s /usr/bin/clang-tidy-13 /usr/bin/clang-tidy
  pip install cmakelang

  # Put smash on PATH in a stable location too (nice for humans + scripts)
  install -d /usr/local/bin
  install -m 0755 ${MNT_DIR}/smash_bin/smash /usr/local/bin/smash
EOF

WORKDIR /workspace

# Set a few other environment variables (just to be sure which locale is used)
# Set the locations of the SMASH sources and build directory for the variables used by FindSMASH.cmake

ENV SMASH_DIR=${PROJECT_DIR}/smash
ENV SMASH_BUILD_DIR=${MNT_DIR}/smash_bin
ENV LC_ALL=en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US.UTF-8
ENV PROMPT_CONTAINER_NAME='electra'

# Set a nice prompt for bash and singularity environments
RUN <<'EOF'
  set -eux
  COMMON_PS1='${PROMPT_CONTAINER_NAME:-SMASH} - \D{%d.%m.%y %H:%M:%S} \001\033[1;94m\002\w\001\033[0m\002 \$ '
  printf "\n\nexport PS1='🔬 %s'\n" "${COMMON_PS1}" >> ~/.bashrc
  mkdir -p /.singularity.d/env
  CUSTOM_ENV=/.singularity.d/env/99-zz_custom_env.sh
  printf "%s\n\n\nexport PS1='📦 %s'\n\n"\
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
echo

exec "$@"
EOF

RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["/bin/bash"]