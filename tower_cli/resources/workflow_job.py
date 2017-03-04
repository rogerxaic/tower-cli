# Copyright 2017 Ansible by Red Hat
# Alan Rominger <arominge@redhat.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import click

from tower_cli import models, resources, get_resource
from tower_cli.api import client
from tower_cli.utils import debug, types, parser


class Resource(models.ExeResource):
    cli_help = 'Launch or monitor workflow jobs.'
    endpoint = '/workflow_jobs/'

    workflow_job_template = models.Field(
        key='-W',
        type=types.Related('workflow'),
        display=True
    )
    extra_vars = models.Field(
        type=types.Variables(), required=False, display=False,
        multiple=True
    )
    created = models.Field(required=False, display=True)
    status = models.Field(required=False, display=True)

    def lookup_stdout(self, pk=None, start_line=None, end_line=None):
        """
        Internal method that lies to our `monitor` method by returning
        a scorecard for the workflow job where the standard out
        would have been expected.
        """
        uj_res = get_resource('unified_jobs')
        # Filters
        #  - limit search to jobs spawned as part of this workflow job
        #  - order in the order in which they should add to the list
        #  - only include final job states
        query_params = (('unified_job_node__workflow_job', pk),
                        ('order_by', 'finished'),
                        ('status__in', 'successful,failed,error'))
        jobs_list = uj_res.list(all_pages=True, query=query_params)['results']
        N = len(jobs_list)

        start_range = start_line
        if start_line is None:
            start_range = 0
        elif start_line > N:
            start_range = N
        
        end_range = end_line
        if end_line is None or end_line > N:
            end_range = N

        lines = []
        for i in range(start_range, end_range):
            job = jobs_list[i]
            lines.append(
                '{0: <20} {1: <10} at {2: <20} in {3: <10} seconds'.format(
                job['name'][:20], job['status'][:10].upper(),
                job['finished'][:20],
                job['elapsed']
            ))
        return_content = '\n'.join(lines)
        if len(lines) > 0:
            return_content += '\n'
        return return_content

    @resources.command(use_fields_as_options=False)
    @click.argument('workflow_job', type=types.Related('workflow_job'))
    def scorecard(self, workflow_job):
        """Print a summary of the outcomes of jobs in the workflow"""
        click.echo(self.lookup_stdout(workflow_job))
        return {'changed': False}

    @resources.command(
        use_fields_as_options=('workflow_job_template', 'extra_vars')
    )
    @click.option('--monitor', is_flag=True, default=False,
                  help='If sent, immediately calls monitor on the newly '
                       'launched workflow job rather than exiting.')
    @click.option('--timeout', required=False, type=int,
                  help='If provided with --monitor, this command (not the job)'
                       ' will time out after the given number of seconds. '
                       'Does nothing if --monitor is not sent.')
    def launch(self, workflow_job_template=None, monitor=False, timeout=None,
               extra_vars=None, **kwargs):
        """Launch a new workflow job based on a workflow job template.

        Creates a new workflow job in Ansible Tower, starts it, and
        returns back an ID in order for its status to be monitored.
        """
        if len(extra_vars) > 0:
            kwargs['extra_vars'] = parser.process_extra_vars(extra_vars)

        debug.log('Launching the workflow job.', header='details')
        self._pop_none(kwargs)
        post_response = client.post('workflow_job_templates/{}/launch/'.format(
            workflow_job_template), data=kwargs).json()

        workflow_job_id = post_response['id']
        post_response['changed'] = True

        if monitor:
            return self.monitor(workflow_job_id, timeout=timeout)

        return post_response
