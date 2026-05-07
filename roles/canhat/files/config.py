import configparser
import os

CONFIG_PATH = os.getenv("VB_CONFIG_PATH", "/opt/voltbro/config.ini")

config = configparser.ConfigParser()
config.read(CONFIG_PATH)

__all__ = ["config"]
