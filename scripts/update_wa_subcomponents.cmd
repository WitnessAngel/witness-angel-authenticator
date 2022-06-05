echo "This script forces updates of wacryptolib/wacomponents to their latest stable versions for WANVR"
pip uninstall -y wacryptolib wacomponents
pip install git+https://github.com/WitnessAngel/witness-angel-cryptolib.git@wakeygen_stable
pip install git+https://github.com/WitnessAngel/witness-angel-components.git@wakeygen_stable