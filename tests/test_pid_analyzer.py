#  Copyright 2024 Switch
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

import json
import unittest
from pathlib import Path
from typing import List, Dict
from unittest import mock
import pid_resolver_lib
from pid_resolver_lib import PublicationInfo
from pid_resolver_lib.pid_analyzer import AuthorInfo, OrcidProfile


class TestPidAnalyzer(unittest.IsolatedAsyncioTestCase):
    def test_analyze_doi_record_crossref(self):
        # https://medium.com/@durgaswaroop/writing-better-tests-in-python-with-pytest-mock-part-2-92b828e1453c
        with mock.patch('pid_resolver_lib.pid_analyzer.read_from_cache') as mock_read_from_cache:

            with open('tests/testdata/crossref_test.xml') as f:
                crossref_xml = f.read()

            mock_read_from_cache.return_value = crossref_xml

            res: PublicationInfo | None = pid_resolver_lib.pid_analyzer.analyze_doi_record_crossref(Path(), '10.2196/38754', {})

            assert res is not None

            assert res.doi == '10.2196/38754'
            assert res.title == 'Practices and Attitudes of Bavarian Stakeholders Regarding the Secondary Use of Health Data for Research Purposes During the COVID-19 Pandemic: Qualitative Interview Study'
            assert len(res.authors) == 6

            assert res.authors[0].orcid == '0000-0002-5726-7633'
            assert res.authors[0].given_name == 'Alena'
            assert res.authors[0].family_name == 'Buyx'

    def test_analyze_doi_record_datacite(self):
        # https://medium.com/@durgaswaroop/writing-better-tests-in-python-with-pytest-mock-part-2-92b828e1453c
        with mock.patch('pid_resolver_lib.pid_analyzer.read_from_cache') as mock_read_from_cache:

            with open('tests/testdata/datacite_test.json') as f:
                datacite_json = f.read()

            mock_read_from_cache.return_value = datacite_json

            res: PublicationInfo | None = pid_resolver_lib.pid_analyzer.analyze_doi_record_datacite(Path(), '10.5281/zenodo.7908081', {})

            assert res is not None

            assert res.doi == '10.5281/zenodo.7908081'
            assert res.title == 'Initial FAIR assessment in the HeartMed Project'

            assert len(res.authors) == 2
            assert res.authors[0].orcid == '0000-0002-3671-895X'
            assert res.authors[0].given_name == 'Irina'
            assert res.authors[0].family_name == 'Balaur'

    def test_get_orcids_from_resolved_dois(self):

        pub_info = PublicationInfo(
            doi='10.5281/zenodo.7908081',
            title='Initial FAIR assessment in the HeartMed Project',
            authors=[AuthorInfo(
                given_name='Irina',
                family_name='Balaur',
                orcid='0000-0002-3671-895X',
                origin_orcid='doi'
            ), AuthorInfo(
                given_name='Soumyabrata',
                family_name='Ghosh',
                orcid='0000-0003-0659-6733',
                origin_orcid='doi'
            )]
        )

        orcids: List[str] = pid_resolver_lib.get_orcids_from_resolved_dois({'10.5281/zenodo.7908081': pub_info})

        assert len(orcids) == 2
        assert set(orcids) == set(['0000-0002-3671-895X', '0000-0003-0659-6733'])

    def test_get_dois_per_orcid(self):

        def mock_read_from_cache_def(orcid: str, cache_dir: Path):
            with open('tests/testdata/orcid_test.json') as f:
                return f.read()

        # https://medium.com/@durgaswaroop/writing-better-tests-in-python-with-pytest-mock-part-2-92b828e1453c
        with mock.patch('pid_resolver_lib.pid_analyzer.get_keys') as mock_get_keys:
            mock_get_keys.return_value = ['0000-0002-3671-895X']

            with mock.patch('pid_resolver_lib.pid_analyzer.read_from_cache') as mock_read_from_cache:
                mock_read_from_cache.side_effect = mock_read_from_cache_def

                dois_per_orcid: List[Dict] = pid_resolver_lib.get_dois_per_orcid(Path())

                assert len(dois_per_orcid) > 0
                assert dois_per_orcid[0]['id'] == 'https://orcid.org/0000-0002-3671-895X'
                assert set(dois_per_orcid[0]['dois']) == set(['10.52825/cordi.v1i.415', '10.1515/jib-2022-0030', '10.1101/2022.12.17.520865', '10.20944/preprints202212.0209.v1', '10.1038/s41598-021-01618-3', '10.1016/j.jaci.2020.11.032', '10.1038/s41585-020-0355-3', '10.1038/s41585-020-0324-x', '10.1093/bioinformatics/btz969', '10.1515/jib-2019-0022', '10.1093/bib/bby099', '10.1038/s41540-018-0059-y', '10.1186/s12918-018-0556-z', '10.1093/bioinformatics/btw731', '10.1186/s12859-016-1394-x', '10.1089/cmb.2016.0095', '10.1186/s13040-016-0102-8', '10.1007/978-1-4939-3283-2_3', '10.1049/iet-syb.2015.0078', '10.1049/iet-syb.2015.0048', '10.1109/bibm.2014.6999255', '10.1109/bibm.2014.6999256', '10.1109/bibm.2014.6999254', '10.1109/ems.2013.27', '10.1007/s12539-013-0172-y', '10.1007/978-3-319-00395-5_126'])

    def test_group_dois_per_orcid(self):
        dois_per_orcid = [
            {'id': 'https://orcid.org/0000-0002-3671-895X', 'givenName': 'Irina', 'familyName': 'Balaur', 'dois': ['10.52825/cordi.v1i.415', '10.1515/jib-2022-0030', '10.1101/2022.12.17.520865', '10.20944/preprints202212.0209.v1', '10.1038/s41598-021-01618-3', '10.1016/j.jaci.2020.11.032', '10.1038/s41585-020-0355-3', '10.1038/s41585-020-0324-x', '10.1093/bioinformatics/btz969', '10.1515/jib-2019-0022', '10.1093/bib/bby099', '10.1038/s41540-018-0059-y', '10.1186/s12918-018-0556-z', '10.1093/bioinformatics/btw731', '10.1186/s12859-016-1394-x', '10.1089/cmb.2016.0095', '10.1186/s13040-016-0102-8', '10.1007/978-1-4939-3283-2_3', '10.1049/iet-syb.2015.0078', '10.1049/iet-syb.2015.0048', '10.1109/bibm.2014.6999255', '10.1109/bibm.2014.6999256', '10.1109/bibm.2014.6999254', '10.1109/ems.2013.27', '10.1007/s12539-013-0172-y', '10.1007/978-3-319-00395-5_126']},
            {'id': 'https://orcid.org/0000-0000-0000-0000', 'givenName': 'Fictious', 'familyName': 'Person',
             'dois': ['10.52825/cordi.v1i.415']}
        ]

        grouped = pid_resolver_lib.group_orcids_per_doi(dois_per_orcid)

        assert len(grouped['10.52825/cordi.v1i.415']) == 2
        assert set(grouped['10.52825/cordi.v1i.415']) == set([OrcidProfile(id='https://orcid.org/0000-0002-3671-895X', given_name='Irina', family_name='Balaur'), OrcidProfile(id='https://orcid.org/0000-0000-0000-0000', given_name='Fictious', family_name='Person')])





