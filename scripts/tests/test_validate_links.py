# -*- coding: utf-8 -*-

import os
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from unittest.mock import patch

from validate.links import find_links_in_text
from validate.links import check_duplicate_links
from validate.links import check_if_link_is_working
from validate.links import fake_user_agent
from validate.links import get_host_from_link
from validate.links import has_cloudflare_protection


class FakeResponse():
    def __init__(self, code: int, headers: dict, text: str) -> None:
        self.status_code = code
        self.headers = headers
        self.text = text


class TestValidateLinks(unittest.TestCase):

    def setUp(self):
        self.duplicate_links = [
            'https://www.example.com',
            'https://www.example.com',
            'https://www.example.com',
            'https://www.anotherexample.com',
        ]
        self.no_duplicate_links = [
            'https://www.firstexample.com',
            'https://www.secondexample.com',
            'https://www.anotherexample.com',
        ]

        self.code_200 = 200
        self.code_403 = 403
        self.code_503 = 503

        self.cloudflare_headers = {'Server': 'cloudflare'}
        self.no_cloudflare_headers = {'Server': 'google'}

        self.text_with_cloudflare_flags = '403 Forbidden Cloudflare We are checking your browser...'
        self.text_without_cloudflare_flags = 'Lorem Ipsum'

    def test_find_link_in_text(self):
        text = """
            # this is valid

            http://example.com?param1=1&param2=2#anchor
            https://www.example.com?param1=1&param2=2#anchor
            https://www.example.com.br
            https://www.example.com.gov.br
            [Example](https://www.example.com?param1=1&param2=2#anchor)
            lorem ipsum https://www.example.com?param1=1&param2=2#anchor
            https://www.example.com?param1=1&param2=2#anchor lorem ipsum

            # this not is valid

            example.com
            https:example.com
            https:/example.com
            https//example.com
            https//.com
        """

        links = find_links_in_text(text)

        self.assertIsInstance(links, list)
        self.assertEqual(len(links), 7)

        for link in links:
            with self.subTest():
                self.assertIsInstance(link, str)

    def test_find_link_in_text_with_invalid_argument(self):
        with self.assertRaises(TypeError):
            find_links_in_text()
            find_links_in_text(1)
            find_links_in_text(True)

    def test_if_check_duplicate_links_has_the_correct_return(self):
        result_1 = check_duplicate_links(self.duplicate_links)
        result_2 = check_duplicate_links(self.no_duplicate_links)

        self.assertIsInstance(result_1, tuple)
        self.assertIsInstance(result_2, tuple)

        has_duplicate_links, links = result_1
        no_duplicate_links, no_links = result_2

        self.assertTrue(has_duplicate_links)
        self.assertFalse(no_duplicate_links)

        self.assertIsInstance(links, list)
        self.assertIsInstance(no_links, list)

        self.assertEqual(len(links), 2)
        self.assertEqual(len(no_links), 0)

    def test_if_fake_user_agent_has_a_str_as_return(self):
        user_agent = fake_user_agent()
        self.assertIsInstance(user_agent, str)

    def test_get_host_from_link(self):
        links = [
            'example.com',
            'https://example.com',
            'https://www.example.com',
            'https://www.example.com.br',
            'https://www.example.com/route',
            'https://www.example.com?p=1&q=2',
            'https://www.example.com#anchor'
        ]

        for link in links:
            host = get_host_from_link(link)

            with self.subTest():
                self.assertIsInstance(host, str)

                self.assertNotIn('://', host)
                self.assertNotIn('/', host)
                self.assertNotIn('?', host)
                self.assertNotIn('#', host)

        with self.assertRaises(TypeError):
            get_host_from_link()

    def test_has_cloudflare_protection_with_code_403_and_503_in_response(self):
        resp_with_cloudflare_protection_code_403 = FakeResponse(
            code=self.code_403,
            headers=self.cloudflare_headers,
            text=self.text_with_cloudflare_flags
        )

        resp_with_cloudflare_protection_code_503 = FakeResponse(
            code=self.code_503,
            headers=self.cloudflare_headers,
            text=self.text_with_cloudflare_flags
        )

        result1 = has_cloudflare_protection(resp_with_cloudflare_protection_code_403)
        result2 = has_cloudflare_protection(resp_with_cloudflare_protection_code_503)

        self.assertTrue(result1)
        self.assertTrue(result2)

    def test_has_cloudflare_protection_when_there_is_no_protection(self):
        resp_without_cloudflare_protection1 = FakeResponse(
            code=self.code_200,
            headers=self.no_cloudflare_headers,
            text=self.text_without_cloudflare_flags
        )

        resp_without_cloudflare_protection2 = FakeResponse(
            code=self.code_403,
            headers=self.no_cloudflare_headers,
            text=self.text_without_cloudflare_flags
        )

        resp_without_cloudflare_protection3 = FakeResponse(
            code=self.code_503,
            headers=self.no_cloudflare_headers,
            text=self.text_without_cloudflare_flags
        )

        result1 = has_cloudflare_protection(resp_without_cloudflare_protection1)
        result2 = has_cloudflare_protection(resp_without_cloudflare_protection2)
        result3 = has_cloudflare_protection(resp_without_cloudflare_protection3)

        self.assertFalse(result1)
        self.assertFalse(result2)
        self.assertFalse(result3)


class TestValidateLinkRedirects(unittest.TestCase):

    def setUp(self):
        # These HTTP fixtures must stay on loopback even in a proxied runner.
        proxy_bypass = patch.dict(os.environ, {
            'NO_PROXY': '127.0.0.1',
            'no_proxy': '127.0.0.1',
        })
        proxy_bypass.start()
        self.addCleanup(proxy_bypass.stop)

    def serve(self, respond):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                respond(self)

            def log_message(self, format, *args):
                pass

        server = HTTPServer(('127.0.0.1', 0), Handler)
        worker = Thread(target=server.serve_forever,
                        kwargs={'poll_interval': 0.01}, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(worker.join)
        self.addCleanup(server.shutdown)
        return '127.0.0.1:{}'.format(server.server_port)

    def redirect_fixture(self, status):
        received = []

        def target(request):
            host = request.headers.get('Host')
            received.append(('target', host))
            request.send_response(status if host == target_host else 421)
            request.send_header('Content-Length', '0')
            request.end_headers()

        target_host = self.serve(target)

        def source(request):
            received.append(('source', request.headers.get('Host')))
            request.send_response(302)
            request.send_header('Location', 'http://{}/target'.format(target_host))
            request.send_header('Content-Length', '0')
            request.end_headers()

        source_host = self.serve(source)
        link = 'http://{}/source'.format(source_host)
        expected = [('source', source_host), ('target', target_host)]
        return link, received, expected

    def test_redirect_uses_each_request_authority_for_host(self):
        link, received, expected = self.redirect_fixture(200)

        result = check_if_link_is_working(link)

        self.assertEqual(received, expected)
        self.assertEqual(result, (False, ''))

    def test_redirect_terminal_http_errors_still_fail(self):
        for status in (404, 503):
            with self.subTest(status=status):
                link, received, expected = self.redirect_fixture(status)

                result = check_if_link_is_working(link)

                self.assertEqual(received, expected)
                self.assertEqual(result, (True, 'ERR:CLT: {} : {}'.format(status, link)))
