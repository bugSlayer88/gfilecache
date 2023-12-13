import send_job
import SubmitHoudiniToDeadlineFunctions
import hou
import sys
import os
import json
from pprint import pprint


def get_all_eval_nodes(kwargs):
    parent = kwargs['node']

    find_pyro = [ x for x in parent.inputAncestors() if 'pyrosolver' in x.type().name() ]
    find_dop = [ x for x in parent.inputAncestors() if 'dopnet' in x.type().name() ]

    if find_pyro:
        return find_pyro
    if find_dop:
        return find_dop
    else:
        return None

def get_nondefault_parms(node_to_eval):
    # # get parms of main node
    main_node_parms = []
    for parm in node_to_eval.allParms():
        if parm.isAtDefault() == False:
            main_node_parms.append(parm.path())

    # get parms of child nodes
    child_nodes = list(node_to_eval.children())

    child_nodes_parms = []
    for i in range(len(child_nodes)):
        for parm in child_nodes[i].parms():
            if parm.isAtDefault() == False:
                child_nodes_parms.append(parm.path())

    all_node_parms = main_node_parms + child_nodes_parms

    return all_node_parms

def create_parm_list(node_to_eval):
    for parm in node_to_eval.allParms():
        yield parm.path()

def eval_parms_list(node_to_eval):
    parm_list = list(get_nondefault_parms(node_to_eval))

    eval_list = []
    for i in range(len(parm_list)):
        parm_val = node_to_eval.evalParm(parm_list[i])
        eval_list.append(parm_val)

    return eval_list

def create_parm_dict(parm_list, eval_list):
    parm_dict = dict(zip(parm_list, eval_list))
    return parm_dict



