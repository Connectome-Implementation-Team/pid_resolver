import unittest
import pid_resolver_lib
from aioresponses import aioresponses
import json
import aiohttp


class TestDoiRaHandler(unittest.IsolatedAsyncioTestCase):
    def test_get_registration_agency_prefixes(self):

        dois = ['10.1016/j.jaci.2020.11.032', '10.1038/s41585-020-0355-3', '10.1038/s41585-020-0324-x']

        prefixes = pid_resolver_lib.doi_ra_handler.get_registration_agency_prefixes(dois)

        assert len(prefixes) == 2
        assert set(prefixes) == set(['10.1016', '10.1038'])

    async def test__make_registration_agency_prefix_request(self):

        mocked_resp = [{
                "DOI": "10.1108",
                "RA": "Crossref"
            }]

        with aioresponses() as mocked:
            mocked.get('https://doi.org/ra/10.1108', status=200, body=json.dumps(mocked_resp))
            session = aiohttp.ClientSession()

            response = await pid_resolver_lib.doi_ra_handler._make_registration_agency_prefix_request(session, '10.1108')

            await session.close()

            assert response is not None
            assert response['DOI'] == '10.1108'
            assert response['RA'] == 'Crossref'



    def test_filter_prefixes_by_registration_agency(self):

        doi_ras = [
            {
                "DOI": "10.1108",
                "RA": "Crossref"
            },
            {
                "DOI": "10.2314",
                "RA": "DataCite"
            },
            {
                "DOI": "10.110",
                "status": "DOI does not exist"
            }
        ]


        filtered_prefixes = pid_resolver_lib.doi_ra_handler.filter_prefixes_by_registration_agency(doi_ras, 'Crossref')

        assert len(filtered_prefixes) == 1
        assert(set(filtered_prefixes)) == set(['10.1108'])

    def test_filter_dois_by_prefixes(self):

        dois = ['10.1016/j.jaci.2020.11.032', '10.1038/s41585-020-0355-3', '10.1038/s41585-020-0324-x']

        filtered = pid_resolver_lib.doi_ra_handler.filter_dois_by_prefixes(dois, ['10.1038'])

        assert len(filtered) == 2
        assert set(filtered) == set(['10.1038/s41585-020-0355-3', '10.1038/s41585-020-0324-x'])
