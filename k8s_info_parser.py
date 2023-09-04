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
    labels: Dict[str, str]

    def __init__(self, name: str):
        self.name = name
        self.capacity = {}
        self.allocatable = {}
        self.allocated = {}
        self.labels = {}

    @property
    def capacity_nvidia_gpu(self):
        try:
            return int(self.capacity.get('nvidia.com/gpu', '0'))
        except ValueError:
            return 0

    @property
    def allocatable_nvidia_gpu(self) -> int:
        try:
            return int(self.allocatable.get('nvidia.com/gpu', '0'))
        except ValueError:
            return 0

    @property
    def allocated_nvidia_gpu(self) -> int:
        try:
            allocated_resource = self.allocated.get('nvidia.com/gpu', None)
            if isinstance(allocated_resource, K8sAllocatedResource):
                return int(allocated_resource.limits)
            return 0
        except ValueError:
            return 0

    @property
    def available_nvidia_gpu(self) -> int:
        return self.allocatable_nvidia_gpu - self.allocated_nvidia_gpu


@dataclass
class K8sPodInfo:
    name: str
    namespace: str
    node_name: str
    used_nvidia_gpus: int


K8S_ALLOCATED_RESOURCES = 'Allocated resources:'
K8S_SYSTEM_INFO = 'System Info:'
K8S_ALLOCATABLE = 'Allocatable:'
K8S_CAPACITY = 'Capacity:'
K8S_EVENTS = 'Events:'
K8S_NAME = 'Name:'
K8S_LABELS = 'Labels:'
K8S_ANNOTATIONS = 'Annotations:'

def str_after_keyword(s: str, keyword: str) -> Optional[str]:
    pos = s.find(keyword)
    if pos <= 0:
        return None
    if pos > 0:
        if not s[pos-1].isspace():
            return None
    return s[pos+len(keyword):]

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
        elif cur_token == K8S_LABELS:
            mode = cur_token
            key_value_str = str_after_keyword(line_s, K8S_LABELS)
            if key_value_str is not None:
                key_value = key_value_str.strip().split('=', maxsplit=1)
                cur_descr.labels.clear()
                if len(key_value) == 2:
                    cur_descr.labels[key_value[0]] = key_value[1]
        elif cur_token == K8S_ANNOTATIONS:
            mode = None # End of labels
        elif (line_s.startswith(K8S_SYSTEM_INFO) and len(tokens) == 2) or cur_token == K8S_EVENTS:
            mode = None
        elif line_s.startswith(K8S_ALLOCATED_RESOURCES) and len(tokens) == 2:
            mode = K8S_ALLOCATED_RESOURCES
        else:
            if mode == K8S_LABELS:
                key_value = line_s.split('=', maxsplit=1)
                if len(key_value) == 2:
                    cur_descr.labels[key_value[0]] = key_value[1]
            elif (mode == K8S_CAPACITY or mode == K8S_ALLOCATABLE) and len(tokens) >= 2 and len(tokens[0]) >= 2:
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
        if len(tokens) >= 3:
            try:
                used_nvidia_gpus = int(tokens[3] if len(tokens) > 3 else '0')
            except ValueError:
                used_nvidia_gpus = 0
            pod_infos.append(
                K8sPodInfo(name=tokens[1], namespace=tokens[0], node_name=tokens[2], used_nvidia_gpus=used_nvidia_gpus))
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
        print('Labels:')
        pprint_dict(descr.labels)
        print('---')

    for pod_info in pod_info_list:
        print(pod_info)
