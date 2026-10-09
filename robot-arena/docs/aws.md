# Evolving a league on a large instance

One hour of lineage evolution on a 192-vCPU box (c7i.48xlarge, us-east-1, about 8.6 USD/h),
as run on 2026-10-08. The founders keep their lives; mutants of their bodies and genes are
born with newborn brains, raised in the nursery, and fight in 32 royales at a time.

```sh
# launch (Ubuntu 24.04, 100 GB gp3), then wait for SSH
aws ec2 run-instances --image-id <ubuntu-24.04 ami> --instance-type c7i.48xlarge \
  --key-name <key> --security-group-ids <sg with port 22 from your ip> --subnet-id <subnet> \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":100,"VolumeType":"gp3"}}]' \
  --instance-initiated-shutdown-behavior terminate

# on the box
sudo apt-get install -y python3-venv rsync
python3 -m venv ~/arena-venv && ~/arena-venv/bin/pip install cadence-net==0.79.0 pytest

# from the laptop: the code and the trained league (replays excluded)
rsync -az --exclude .venv --exclude runs --exclude .git --exclude 'league/fights' ./ ubuntu@<ip>:~/cadence-robot-arena/

# on the box: keep the three best, breed and fight for an hour, keep the best twelve
cd ~/cadence-robot-arena && export OMP_NUM_THREADS=1
~/arena-venv/bin/python -m arena --league league retire --random Roller Hexapod Scorpion Cart Tumbler
nohup ~/arena-venv/bin/python -m arena --league league evolve --founders Mantis,Dozer,Crab \
  --population 192 --elite 64 --nursery-moments 80000 --rounds 30 --generations 12 --size 6 \
  --parallel 32 --inner-workers 6 --workers 192 --hours 1.0 --keep 12 --seed 1 > evolve.log 2>&1 &

# back on the laptop, afterwards: the league without its replays, then a showcase of the survivors
rsync -az ubuntu@<ip>:~/cadence-robot-arena/league/ league-evolved/
.venv/bin/python -m arena --league league-evolved royale --fights 6 --size 6
.venv/bin/python -m arena --league league-evolved dashboard
aws ec2 terminate-instances --instance-ids <id>
```

Sizing: a fight process with six brain workers keeps six vCPUs busy, so a population of 192
in 32 simultaneous fights fills the box; a round of 1,200-moment fights takes about ten
seconds, a generation's nursery of 128 newborns at 80,000 moments about three minutes.
Every generation ranks the population by its mean placement score in that generation's
fights, keeps the best third with their brains, retires the rest and fills the places with
mutants of the survivors. Terminate the instance when the league is back.
