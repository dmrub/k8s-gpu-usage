#!/usr/bin/env python3
import os.path
import pprint
from dataclasses import dataclass
from typing import Optional, List, Dict


@dataclass
class K8sAllocatedResource:
    requests: str
    limits: str


@dataclass
class K8sNodeDescr:
    name: str
    capacity: Dict[str, str]
    allocatable: Dict[str, str]
    allocated: Dict[str, K8sAllocatedResource]

    def __init__(self, name: str):
        self.name = name
        self.capacity = {}
        self.allocatable = {}
        self.allocated = {}

@dataclass
class K8sPodInfo:
    name: str
    namespace: str
    used_nvidia_gpus: str

K8S_ALLOCATED_RESOURCES = 'Allocated resources:'
K8S_SYSTEM_INFO = 'System Info:'
K8S_ALLOCATABLE = 'Allocatable:'
K8S_CAPACITY = 'Capacity:'
K8S_EVENTS = 'Events:'
K8S_NAME = 'Name:'


def k8s_parse_node_description(text):
    cur_descr: Optional[K8sNodeDescr] = None
    descr_list: List[K8sNodeDescr] = []
    cur_token: Optional[str] = None
    last_token: Optional[str] = None
    mode: Optional[str] = None
    for line in text.splitlines():
        line_s = line.strip()
        if not line_s:
            continue
        tokens = line_s.split()
        if not tokens:
            continue
        last_token = cur_token
        cur_token = tokens[0]
        if cur_token == K8S_NAME:
            if cur_descr is not None:
                descr_list.append(cur_descr)
            cur_descr = K8sNodeDescr(tokens[1])
            mode = None
        elif cur_token == K8S_CAPACITY:
            mode = cur_token
        elif cur_token == K8S_ALLOCATABLE:
            mode = cur_token
        elif (line_s.startswith(K8S_SYSTEM_INFO) and len(tokens) == 2) or cur_token == K8S_EVENTS:
            mode = None
        elif line_s.startswith(K8S_ALLOCATED_RESOURCES) and len(tokens) == 2:
            mode = K8S_ALLOCATED_RESOURCES
        else:
            if (mode == K8S_CAPACITY or mode == K8S_ALLOCATABLE) and len(tokens) >= 2 and len(tokens[0]) >= 2:
                key = tokens[0][:-1]  # remove last ':'
                value = tokens[1]
                if mode == K8S_CAPACITY:
                    cur_descr.capacity[key] = value
                else:
                    cur_descr.allocatable[key] = value
            elif mode == K8S_ALLOCATED_RESOURCES:
                if (len(tokens) == 3 or len(tokens) == 5) and not tokens[0].startswith('-') and tokens[0] != 'Resource':
                    if len(tokens) == 3:
                        cur_descr.allocated[tokens[0]] = K8sAllocatedResource(requests=tokens[1], limits=tokens[2])
                    elif len(tokens) == 5:  # with % values
                        cur_descr.allocated[tokens[0]] = K8sAllocatedResource(requests=tokens[1], limits=tokens[3])

    if cur_descr is not None:
        descr_list.append(cur_descr)
    return descr_list

def k8s_parse_pod_info(text):
    pod_infos: List[K8sPodInfo] = []
    for line in text.splitlines():
        line_s = line.strip()
        if not line_s:
            continue
        tokens = line_s.split(',')
        if not tokens:
            continue
        if len(tokens) >= 2:
            pod_infos.append(K8sPodInfo(name=tokens[1], namespace=tokens[0], used_nvidia_gpus=tokens[2] if len(tokens) > 2 else '0'))
    return pod_infos

if __name__ == '__main__':

    k8s_node_description_path = os.path.join('instance', 'k8s-node-description.txt')
    with open(k8s_node_description_path, 'r') as f:
        k8s_node_description_text = f.read()
    print(k8s_node_description_text)
    descr_list = k8s_parse_node_description(k8s_node_description_text)

    k8s_pod_info_path = os.path.join('instance', 'k8s-pod-info.txt')
    with open(k8s_pod_info_path, 'r') as f:
        k8s_pod_info_text = f.read()
    print(k8s_pod_info_text)
    pod_info_list = k8s_parse_pod_info(k8s_pod_info_text)


    def pprint_dict(d):
        for k, v in d.items():
            print("{0}: {1}".format(k, pprint.pformat(v, depth=5)))


    for descr in descr_list:
        print(descr.name)
        print('Capacity:')
        pprint_dict(descr.capacity)
        print('---')
        print('Allocatable:')
        pprint_dict(descr.allocatable)
        print('---')
        print('Allocated:')
        pprint_dict(descr.allocated)
        print('---')

    for pod_info in pod_info_list:
        print(pod_info)
