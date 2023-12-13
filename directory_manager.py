import os
import hou


def build_sopoutput(render_node):
    # put together the path the cache will render to
    hip_src = hou.expandString("$HIP")
    cache_name = hou.expandString("$OS")
    cache_version = hou.evalParm("cacheversion")
    frame_number = hou.expandString("$F")
    # create the cache file title here:
    cache_file = "{}.v{}.{}.bgeo.sc".format(cache_name,cache_version,frame_number)
    # cache_dir_full looks like this: W:/hou_cache/hipfiles/geo/pigcache/v1/pigcache.1.bgeo.sc
    cache_dir_full = hip_src + '/geo/' + cache_name + '/' + 'v' + str(cache_version) + '/' + cache_file

    return cache_dir_full

def create_directory(render_node):
    cache_dir_fullpath = render_node.evalParm("sopoutput")
    # get the parent folder path 
    cache_dir_drop_file = os.path.split(cache_dir_fullpath)
    create_cache_dir = cache_dir_drop_file[0] + '/'

    if not os.path.exists(create_cache_dir):
        os.makedirs(create_cache_dir)

    return create_cache_dir

def read_in_cache_dir(render_node):
    # get the path to read the cache in from
    hip_src = hou.expandString("$HIP")
    cache_name = hou.expandString("$OS")
    read_cache_version = hou.evalParm("readcacheversion")
    frame_number = hou.expandString("$F")
    # source the cache file title here (this needs to match from build_sopoutput function above):
    cache_file = "{}.v{}.{}.bgeo.sc".format(cache_name,read_cache_version,frame_number)

    read_cache_dir = hip_src + '/geo/' + cache_name + '/' + 'v' + str(read_cache_version) + '/' + cache_file

    return read_cache_dir

def get_txt_file(render_node):
    # get the path to read in the txt file from
    hip_src = hou.expandString("$HIP")
    cache_name = hou.expandString("$OS")
    cache_version = hou.evalParm("reviewcacheversion")

    cache_txt_file = "cache_settings.txt"

    cache_txt_dir = hip_src + '/geo/' + cache_name + '/' + 'v' + str(cache_version) + '/' + cache_txt_file

    return cache_txt_dir

