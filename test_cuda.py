import torch
print("Torch version:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())
print("Device count:", torch.cuda.device_count())
if torch.cuda.device_count() > 0:
    print("Device 0:", torch.cuda.get_device_name(0))
else:
    print("Device 0: No GPU")
print("Torch CUDA version:", torch.version.cuda)