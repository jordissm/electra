#!/bin/bash

#SBATCH -J electra:analysis
#SBATCH -A qgp
#SBATCH -p qgp
#SBATCH -t 12:00:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH -o analysis.out
#SBATCH -e analysis.err

#LC_ALL=C find runs/6/ehijing/events -name '*.oscar' > particle_lists_files.txt
#LC_ALL=C find runs/5/ehijing/events -name 'particle_lists.oscar' > particle_lists_files.txt

./analyze_oscar_dndptdz --meta runs/6/ehijing/DISKinematics.meta.jsonl --file-list particle_lists_files.txt --out dndptdz.yoda --pt-nbins 10
