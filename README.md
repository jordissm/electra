# ELECTRA

## Pre-requisites

## Usage

'''
docker buildx build --platform=linux/amd64 --load -t electra:latest -f Dockerfile .
'''

'''
 docker run -it --name electra --platform=linux/amd64 --mount type=bind,source=$PWD,target=/SMASH/mnt electra:latest
'''

'''
docker start -ai electra
'''

'''
./smash -i /SMASH/mnt/input/config_pp.yaml -o /SMASH/mnt/output/smash/pp_0d0
'''

'''
python3 shard_profiles.py --in-dir input/smash/xsec_scaling_factor_profiles/ --out-root run/profiles --out-index run/profiles/profiles.jsonl --mode copy
'''