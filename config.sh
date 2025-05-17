cd /tmp/

sudo rm -rf omnipkg-app/

git clone https://www.github.com/maibloom/omnipkg-app

cd omnipkg-app/

if sudo bash build.sh; then
  omnipkg put install maibloom-builder
else
  echo "running build has failed"
fi