import sys
import os

proto_dir = os.path.dirname(__file__)
if proto_dir not in sys.path:
    sys.path.insert(0, proto_dir)

try:
    from . import hag_pb2, hag_pb2_grpc
except ImportError:
    import hag_pb2
    import hag_pb2_grpc

__all__ = ["hag_pb2", "hag_pb2_grpc"]
