#!/usr/bin/env python3
import os
import pprint
from datetime import datetime

import requests
import subprocess
from flask import (
    Flask,
    Response,
    current_app,
    jsonify,
    render_template,
    request,
    url_for,
)

from flask_reverse_proxy import ReverseProxied
import logging
from k8s_info_parser import k8s_parse_node_description, k8s_parse_pod_info

app = Flask(__name__, instance_relative_config=True)
app.wsgi_app = ReverseProxied(app.wsgi_app)
LOGGER = app.logger
C_ENVIROMENT = dict(os.environ, LC_ALL="C.UTF8", LANGUAGE="C")

DEBUG_MODE = False

# Load default config and override config from an environment variable
app.config.update(
    dict(
        SECRET_KEY=os.urandom(24),
        LOG_FILE=os.path.join(app.instance_path, "app.log"),
        FILE_FOLDER=os.path.join(app.instance_path, "files"),
        PORT=os.environ.get("PORT", 5000),
        MAX_CONTENT_LENGTH=100 * 1024 * 1024,  # Maximal 100 Mb for files
        KUBECTL=os.environ.get("KUBECTL", "/usr/local/bin/kubectl"),
    )
)
app.config.from_envvar("APP_SETTINGS", silent=True)

# ensure the instance folder exists
os.makedirs(app.instance_path, exist_ok=True)

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_INTERNAL_SERVER_ERROR = 500
HTTP_NOT_IMPLEMENTED = 501


def error_response(message, status_code=HTTP_INTERNAL_SERVER_ERROR):
    response = jsonify({"message": message})
    response.status_code = status_code
    return response


def bad_request(message):
    return error_response(message=message, status_code=HTTP_BAD_REQUEST)


def not_found(message):
    return error_response(message=message, status_code=HTTP_NOT_FOUND)


def not_implemented(message):
    return error_response(message=message, status_code=HTTP_NOT_IMPLEMENTED)


class K8sError(Exception):
    def __init__(self, message, stdout=None, stderr=None, oserror=None):
        self.message = message
        self.stdout = stdout
        self.stderr = stderr
        self.oserror = oserror
        super(K8sError, self).__init__(message)


@app.errorhandler(K8sError)
def on_k8s_error(error):
    status = HTTP_INTERNAL_SERVER_ERROR
    return error_response(error.message, status)


@app.errorhandler(requests.exceptions.ConnectionError)
def on_request_exception(error):
    return error_response(message=str(error), status_code=HTTP_INTERNAL_SERVER_ERROR)

@app.template_filter()
def datetime_format(value, format="%d.%m.%y %H:%M"):
    return value.strftime(format)

def k8s_get_info():
    k8s_node_description_path = os.path.join(app.instance_path, "k8s-node-description.txt")
    k8s_node_description_text: str = ""
    if DEBUG_MODE and os.path.exists(k8s_node_description_path):
        with open(k8s_node_description_path, "r") as f:
            k8s_node_description_text = f.read()
        LOGGER.info("Loaded file %s", k8s_node_description_path)
    else:
        cmdargs = [app.config["KUBECTL"], "describe", "nodes", "--all-namespaces"]
        r = subprocess.run(
            cmdargs,
            encoding="utf8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=C_ENVIROMENT,
        )
        if r.returncode != 0:
            raise K8sError(
                'Could not execute command "{}": exit code: {}, error: {}'.format(
                    " ".join(cmdargs), r.returncode, r.stderr
                )
            )
        k8s_node_description_text = r.stdout
        if DEBUG_MODE:
            with open(k8s_node_description_path, "w") as f:
                f.write(k8s_node_description_text)
            LOGGER.info("File %s created", k8s_node_description_path)

    k8s_pod_info_path = os.path.join(app.instance_path, "k8s-pod-info.txt")
    k8s_pod_info_text: str = ""
    if DEBUG_MODE and os.path.exists(k8s_pod_info_path):
        with open(k8s_pod_info_path, "r") as f:
            k8s_pod_info_text = f.read()
        LOGGER.info("Loaded file %s", k8s_pod_info_path)
    else:
        go_template = (
            r'{{range .items}}{{if (eq .status.phase "Running")}}{{$pns:=.metadata.namespace}}'
            r"{{$pname:=.metadata.name}}{{$pnode:=.spec.nodeName}}{{range .spec.containers}}"
            r'{{ with .resources.requests }}{{$gpus:=(index . "nvidia.com/gpu")}}'
            r'{{if $gpus}}{{$pns}}{{","}}{{$pname}}{{","}}{{$pnode}}{{","}}{{$gpus}}{{"\n"}}'
            r"{{end}}{{end}}{{end}}{{end}}{{end}} "
        )
        cmdargs = [
            app.config["KUBECTL"],
            "get",
            "pods",
            "--all-namespaces",
            "-o",
            "go-template",
            "--template",
            go_template,
        ]
        r = subprocess.run(
            cmdargs,
            encoding="utf8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=C_ENVIROMENT,
        )
        if r.returncode != 0:
            raise K8sError(
                'Could not execute command "{}": exit code: {}, error: {}'.format(
                    " ".join(cmdargs), r.returncode, r.stderr
                )
            )
        k8s_pod_info_text = r.stdout
        if DEBUG_MODE:
            with open(k8s_pod_info_path, "w") as f:
                f.write(k8s_pod_info_text)
            LOGGER.info("File %s created", k8s_pod_info_path)

    k8s_node_descr_list = k8s_parse_node_description(k8s_node_description_text)
    k8s_pod_info_list = [pi for pi in k8s_parse_pod_info(k8s_pod_info_text) if pi.used_nvidia_gpus > 0]

    return k8s_node_descr_list, k8s_pod_info_list


@app.route("/")
def index():
    k8s_node_descr_list, k8s_pod_info_list = k8s_get_info()
    return render_template(
        "k8s_gpu_usage.html",
        k8s_node_descr_list=k8s_node_descr_list,
        k8s_pod_info_list=k8s_pod_info_list,
        now=datetime.now()
    )


@app.route("/api/debug/flask/", methods=["GET"])
def debug_flask():
    import urllib

    output = ["Rules:"]
    for rule in current_app.url_map.iter_rules():
        options = {}
        for arg in rule.arguments:
            options[arg] = "[{0}]".format(arg)

        if rule.methods:
            methods = ",".join(rule.methods)
        else:
            methods = "GET"
        url = url_for(rule.endpoint, **options)
        line = urllib.parse.unquote("{:50s} {:20s} {}".format(rule.endpoint, methods, url))
        output.append(line)

    output.append("")
    output.append("Request environment:")
    for k, v in request.environ.items():
        output.append("{0}: {1}".format(k, pprint.pformat(v, depth=5)))

    output.append("")
    output.append("Request vars:")
    output.append("request.path: {}".format(request.path))
    output.append("request.full_path: {}".format(request.full_path))
    output.append("request.script_root: {}".format(request.script_root))
    output.append("request.url: {}".format(request.url))
    output.append("request.base_url: {}".format(request.base_url))
    output.append("request.host_url: {}".format(request.host_url))
    output.append("request.url_root: {}".format(request.url_root))
    output.append("")

    return Response("\n".join(output), mimetype="text/plain")


if __name__ == "__main__":
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
    app.debug = True
    port = int(app.config["PORT"])
    print(app.config)
    print("Running on port {}".format(port))
    app.run(host="0.0.0.0", port=port)
