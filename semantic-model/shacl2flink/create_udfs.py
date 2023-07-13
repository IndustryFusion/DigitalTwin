#
# Copyright (c) 2023 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import os.path
import ruamel.yaml
from lib import utils
import glob


udfdir = 'udf/*/flink_*.py'
udfcrdname = 'udf.yaml'


def main(output_folder='output'):
    yaml = ruamel.yaml.YAML()

    utils.create_output_folder(output_folder)
    udfs_full = glob.glob(udfdir)

    with open(os.path.join(output_folder, udfcrdname), 'w') as f:
        for file in udfs_full:
            with open(file) as fi:
                txt = fi.read()
            file_base = os.path.basename(os.path.splitext(file)[0])
            _, file_name, file_ver = file_base.split('_')
            crd = {}
            crd['apiVersion'] = 'industry-fusion.com/v1alpha1'
            crd['kind'] = 'flinkpythonudf'
            metadata = {}
            metadata['name'] = file_name
            spec = {}
            spec['filename'] = file_name
            spec['version'] = file_ver
            spec['class'] = txt
            crd['metadata'] = metadata
            crd['spec'] = spec
            f.write('---')
            yaml.dump(crd, f)


if __name__ == '__main__':
    main()
