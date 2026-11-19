# -*- coding: utf-8 -*-

import unittest

from validate.format import error_message
from validate.format import get_categories_content
from validate.format import check_alphabetical_order
from validate.format import check_title
from validate.format import check_description, max_description_length
from validate.format import check_auth, auth_keys
from validate.format import check_https, https_keys
from validate.format import check_cors, cors_keys
from validate.format import check_entry
from validate.format import check_file_format, min_entries_per_category, num_segments


class TestValidadeFormat(unittest.TestCase):

    @staticmethod
    def catalog(entries=None, separator='|:---|---:|:---:|---|:---|', preamble=None):
        return (preamble or []) + [
            '## Index',
            '* [Test Category](#test-category)',
            '',
            '### Test Category',
            '| API | Description | Auth | HTTPS | CORS |',
            separator,
        ] + (entries if entries is not None else [
            '| [Alpha](https://alpha.example) | First service | No | Yes | Unknown |',
            '| [Beta](https://beta.example) | Second service | `apiKey` | Yes | Yes |',
            '| [Gamma](https://gamma.example) | Third service | No | No | No |',
        ])

    def test_catalog_ignores_introductory_non_catalog_tables(self):
        preamble = [
            '### Featured services',
            '| Service | Description | Link |',
            '|:---|:---|:---|',
            '| [Example](https://example.test) | Featured service | Try it |',
            '## MCP Servers',
            '| Name | Description | Auth | Transport | Install |',
            '|:---|:---|:---|:---|:---|',
            '| [Tool](https://tool.example) | Agent tool | No | `stdio` | npm |',
        ]
        lines = self.catalog(preamble=preamble)
        self.assertEqual(check_file_format(lines), [])
        categories, locations = get_categories_content(lines)
        self.assertEqual(categories, {'Test Category': ['ALPHA', 'BETA', 'GAMMA']})
        self.assertEqual(locations, {'Test Category': len(preamble) + 3})

    def test_catalog_accepts_markdown_alignment_and_header_rows(self):
        for separator in [
            '|---|---|---|---|---|',
            '|:---|---:|:---:|---|:---|',
            '| :--- | ---: | :---: | --- | :--- |',
        ]:
            with self.subTest(separator=separator):
                self.assertEqual(check_file_format(self.catalog(separator=separator)), [])

    def test_catalog_keeps_validation_of_invalid_api_rows(self):
        lines = self.catalog()
        lines[-1] = '| [Gamma](https://gamma.example) | Third service | No | Unknown | No |'
        self.assertEqual(check_file_format(lines), ['(L009) Unknown is not a valid HTTPS option'])

    def test_catalog_does_not_skip_data_that_looks_like_separator(self):
        lines = self.catalog()
        lines[-1] = '| --- | Valid description | No | Yes | No |'
        self.assertEqual(check_file_format(lines), ['(L009) Title syntax should be "[TITLE](LINK)"'])

    def test_catalog_rejects_extra_columns(self):
        lines = self.catalog()
        lines[-1] = '| [Gamma](https://gamma.example) | Third service | No | Yes | No | Optional | Extra |'
        self.assertEqual(check_file_format(lines), [
            '(L009) entry has too many columns (have 7, maximum 6)'
        ])

    def test_catalog_rejects_extra_boundary_cells_in_table_metadata(self):
        lines = self.catalog()
        lines[4] = '|| API | Description | Auth | HTTPS | CORS ||'
        lines[5] = '||---|---|---|---|---||'
        self.assertEqual(check_file_format(lines), [
            '(L005) entry has too many columns (have 7, maximum 6)',
            '(L006) entry has too many columns (have 7, maximum 6)',
        ])

    def test_catalog_reports_bare_table_delimiter_without_crashing(self):
        lines = self.catalog()
        lines[-1] = '|'
        self.assertEqual(check_file_format(lines), [
            '(L009) entry does not have all the required columns (have 0, need 5)'
        ])

    def test_catalog_allows_documented_optional_postman_column(self):
        lines = self.catalog()
        lines[4] = '| API | Description | Auth | HTTPS | CORS | Call this API |'
        lines[5] = '|:---|:---|:---|:---|:---|:---|'
        lines[6:] = [row + ' [Collection](https://postman.example) |' for row in lines[6:]]
        self.assertEqual(check_file_format(lines), [])

    def test_catalog_reports_empty_description_without_crashing(self):
        lines = self.catalog()
        lines[-1] = '| [Gamma](https://gamma.example) |  | No | Yes | No |'
        errors = check_file_format(lines)
        self.assertIn('(L009) description must not be empty', errors)

    def test_catalog_checks_final_category_minimum_without_counting_metadata(self):
        lines = self.catalog()[:-1]
        self.assertEqual(check_file_format(lines), [
            '(L004) Test Category category does not have the minimum 3 entries (only has 2)'
        ])

    def test_catalog_keeps_ordering_checks_after_ignoring_preamble(self):
        lines = self.catalog(preamble=['### Featured services'])
        lines[-1], lines[-2] = lines[-2], lines[-1]
        self.assertEqual(check_file_format(lines), [
            '(L005) Test Category category is not alphabetical order'
        ])
    
    def test_error_message_return_and_return_type(self):
        line_num_unity = 1
        line_num_ten = 10
        line_num_hundred = 100
        line_num_thousand = 1000

        msg = 'This is a unit test'

        err_msg_unity = error_message(line_num_unity, msg)
        err_msg_ten = error_message(line_num_ten, msg)
        err_msg_hundred = error_message(line_num_hundred, msg)
        err_msg_thousand = error_message(line_num_thousand, msg)

        self.assertIsInstance(err_msg_unity, str)
        self.assertIsInstance(err_msg_ten, str)
        self.assertIsInstance(err_msg_hundred, str)
        self.assertIsInstance(err_msg_thousand, str)

        self.assertEqual(err_msg_unity, '(L002) This is a unit test')
        self.assertEqual(err_msg_ten, '(L011) This is a unit test')
        self.assertEqual(err_msg_hundred, '(L101) This is a unit test')
        self.assertEqual(err_msg_thousand, '(L1001) This is a unit test')

    def test_if_get_categories_content_return_correct_data_of_categories(self):
        fake_contents = [
            '### A',
            'API | Description | Auth | HTTPS | CORS |',
            '|---|---|---|---|---|',
            '| [AA](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
            '| [AB](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
            '',
            '### B',
            'API | Description | Auth | HTTPS | CORS |',
            '|---|---|---|---|---|',
            '| [BA](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
            '| [BB](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |'
        ]

        result = get_categories_content(fake_contents)
        self.assertIsInstance(result, tuple)

        categories, category_line_num = result
        self.assertIsInstance(categories, dict)
        self.assertIsInstance(category_line_num, dict)

        expected_result = ({'A': ['AA', 'AB'], 'B': ['BA', 'BB']}, {'A': 0, 'B': 6})

        for res, ex_res in zip(result, expected_result):

            with self.subTest():
                self.assertEqual(res, ex_res)

    def test_if_check_alphabetical_order_return_correct_msg_error(self):
        correct_lines = [
            '### A',
            'API | Description | Auth | HTTPS | CORS |',
            '|---|---|---|---|---|',
            '| [AA](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
            '| [AB](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
            '',
            '### B',
            'API | Description | Auth | HTTPS | CORS |',
            '|---|---|---|---|---|',
            '| [BA](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
            '| [BB](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |'
        ]

        incorrect_lines = [
            '### A',
            'API | Description | Auth | HTTPS | CORS |',
            '|---|---|---|---|---|',
            '| [AB](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
            '| [AA](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
            '',
            '### B',
            'API | Description | Auth | HTTPS | CORS |',
            '|---|---|---|---|---|',
            '| [BB](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
            '| [BA](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |'
        ]


        err_msgs_1 = check_alphabetical_order(correct_lines)
        err_msgs_2 = check_alphabetical_order(incorrect_lines)

        self.assertIsInstance(err_msgs_1, list)
        self.assertIsInstance(err_msgs_2, list)

        self.assertEqual(len(err_msgs_1), 0)
        self.assertEqual(len(err_msgs_2), 2)

        expected_err_msgs = [
            '(L001) A category is not alphabetical order',
            '(L007) B category is not alphabetical order'
        ]

        for err_msg, ex_err_msg in zip(err_msgs_2, expected_err_msgs):

            with self.subTest():
                self.assertEqual(err_msg, ex_err_msg)
    
    def test_check_title_with_correct_title(self):
        raw_title = '[A](https://www.ex.com)'

        err_msgs = check_title(0, raw_title)

        self.assertIsInstance(err_msgs, list)
        self.assertEqual(len(err_msgs), 0)
        self.assertEqual(err_msgs, [])

    def test_check_title_with_markdown_syntax_incorrect(self):
        raw_title = '[A(https://www.ex.com)'

        err_msgs = check_title(0, raw_title)

        self.assertIsInstance(err_msgs, list)
        self.assertEqual(len(err_msgs), 1)
        
        err_msg = err_msgs[0]
        expected_err_msg = '(L001) Title syntax should be "[TITLE](LINK)"'

        self.assertEqual(err_msg, expected_err_msg)

    def test_check_title_with_api_at_the_end_of_the_title(self):
        raw_title = '[A API](https://www.ex.com)'

        err_msgs = check_title(0, raw_title)
        
        self.assertIsInstance(err_msgs, list)
        self.assertEqual(len(err_msgs), 1)
        
        err_msg = err_msgs[0]
        expected_err_msg = '(L001) Title should not end with "... API". Every entry is an API here!'

        self.assertEqual(err_msg, expected_err_msg)

    def test_check_description_with_correct_description(self):
        desc = 'This is a fake description'

        err_msgs = check_description(0, desc)

        self.assertIsInstance(err_msgs, list)
        self.assertEqual(len(err_msgs), 0)
        self.assertEqual(err_msgs, [])
    
    def test_check_description_with_first_char_is_not_capitalized(self):
        desc = 'this is a fake description'

        err_msgs = check_description(0, desc)

        self.assertIsInstance(err_msgs, list)
        self.assertEqual(len(err_msgs), 1)
        
        err_msg = err_msgs[0]
        expected_err_msg = '(L001) first character of description is not capitalized'

        self.assertIsInstance(err_msg, str)
        self.assertEqual(err_msg, expected_err_msg)
    
    def test_check_description_with_punctuation_in_the_end(self):
        base_desc = 'This is a fake description'
        punctuation = r"""!"#$%&'*+,-./:;<=>?@[\]^_`{|}~"""
        desc_with_punc = [base_desc + punc for punc in punctuation]
        
        for desc in desc_with_punc:

            with self.subTest():
                err_msgs = check_description(0, desc)

                self.assertIsInstance(err_msgs, list)
                self.assertEqual(len(err_msgs), 1)
        
                err_msg = err_msgs[0]
                expected_err_msg = f'(L001) description should not end with {desc[-1]}'

                self.assertIsInstance(err_msg, str)
                self.assertEqual(err_msg, expected_err_msg)

    def test_check_description_that_exceeds_the_character_limit(self):
        long_desc = 'Desc' * max_description_length
        long_desc_length = len(long_desc)

        err_msgs = check_description(0, long_desc)

        self.assertIsInstance(err_msgs, list)
        self.assertEqual(len(err_msgs), 1)

        err_msg = err_msgs[0]
        expected_err_msg = f'(L001) description should not exceed {max_description_length} characters (currently {long_desc_length})'

        self.assertIsInstance(err_msg, str)
        self.assertEqual(err_msg, expected_err_msg)

    def test_check_auth_with_valid_auth(self):
        auth_valid = [f'`{auth}`' for auth in auth_keys if auth != 'No']
        auth_valid.append('No')

        for auth in auth_valid:
            with self.subTest():
                err_msgs = check_auth(0, auth)
                self.assertIsInstance(err_msgs, list)
                self.assertEqual(len(err_msgs), 0)
                self.assertEqual(err_msgs, [])

    def test_check_auth_without_backtick(self):
        auth_without_backtick = [auth for auth in auth_keys if auth != 'No']

        for auth in auth_without_backtick:
            with self.subTest():
                err_msgs = check_auth(0, auth)
                self.assertIsInstance(err_msgs, list)
                self.assertEqual(len(err_msgs), 1)

                err_msg = err_msgs[0]
                expected_err_msg = '(L001) auth value is not enclosed with `backticks`'

                self.assertIsInstance(err_msg, str)
                self.assertEqual(err_msg, expected_err_msg)

    def test_check_auth_with_invalid_auth(self):
        auth_invalid_without_backtick = ['Yes', 'yes', 'no', 'random', 'Unknown']
        auth_invalid_with_backtick = ['`Yes`', '`yes`', '`no`', '`random`', '`Unknown`']

        for auth in auth_invalid_without_backtick:
            with self.subTest():
                err_msgs = check_auth(0, auth)
                self.assertIsInstance(err_msgs, list)
                self.assertEqual(len(err_msgs), 2)

                err_msg_1 = err_msgs[0]
                err_msg_2 = err_msgs[1]

                expected_err_msg_1 = f'(L001) auth value is not enclosed with `backticks`'
                expected_err_msg_2 = f'(L001) {auth} is not a valid Auth option'

                self.assertIsInstance(err_msg_1, str)
                self.assertIsInstance(err_msg_2, str)
                self.assertEqual(err_msg_1, expected_err_msg_1)
                self.assertEqual(err_msg_2, expected_err_msg_2)

        for auth in auth_invalid_with_backtick:
            with self.subTest():
                err_msgs = check_auth(0, auth)
                self.assertIsInstance(err_msgs, list)
                self.assertEqual(len(err_msgs), 1)

                err_msg = err_msgs[0]
                expected_err_msg = f'(L001) {auth} is not a valid Auth option'

                self.assertIsInstance(err_msg, str)
                self.assertEqual(err_msg, expected_err_msg)

    def test_check_https_with_valid_https(self):
        for https in https_keys:
            with self.subTest():
                err_msgs = check_https(0, https)
                self.assertIsInstance(err_msgs, list)
                self.assertEqual(len(err_msgs), 0)
                self.assertEqual(err_msgs, [])

    def test_check_https_with_invalid_https(self):
        invalid_https_keys = ['yes', 'no', 'Unknown', 'https', 'http']

        for https in invalid_https_keys:
            with self.subTest():
                err_msgs = check_https(0, https)
                self.assertIsInstance(err_msgs, list)
                self.assertEqual(len(err_msgs), 1)

                err_msg = err_msgs[0]
                expected_err_msg = f'(L001) {https} is not a valid HTTPS option'

                self.assertIsInstance(err_msg, str)
                self.assertEqual(err_msg, expected_err_msg)

    def test_check_cors_with_valid_cors(self):
        for cors in cors_keys:
            with self.subTest():
                err_msgs = check_cors(0, cors)
                self.assertIsInstance(err_msgs, list)
                self.assertEqual(len(err_msgs), 0)
                self.assertEqual(err_msgs, [])

    def test_check_cors_with_invalid_cors(self):
        invalid_cors_keys = ['yes', 'no', 'unknown', 'cors']

        for cors in invalid_cors_keys:
            with self.subTest():
                err_msgs = check_cors(0, cors)
                self.assertIsInstance(err_msgs, list)
                self.assertEqual(len(err_msgs), 1)

                err_msg = err_msgs[0]
                expected_err_msg = f'(L001) {cors} is not a valid CORS option'

                self.assertIsInstance(err_msg, str)
                self.assertEqual(err_msg, expected_err_msg)

    def test_check_entry_with_correct_segments(self):
        correct_segments = ['[A](https://www.ex.com)', 'Desc', '`apiKey`', 'Yes', 'Yes']

        err_msgs = check_entry(0, correct_segments)
        
        self.assertIsInstance(err_msgs, list)
        self.assertEqual(len(err_msgs), 0)
        self.assertEqual(err_msgs, [])

    def test_check_entry_with_incorrect_segments(self):
        incorrect_segments = ['[A API](https://www.ex.com)', 'desc.', 'yes', 'yes', 'yes']

        err_msgs = check_entry(0, incorrect_segments)
        expected_err_msgs = [
            '(L001) Title should not end with "... API". Every entry is an API here!',
            '(L001) first character of description is not capitalized',
            '(L001) description should not end with .',
            '(L001) auth value is not enclosed with `backticks`',
            '(L001) yes is not a valid Auth option',
            '(L001) yes is not a valid HTTPS option',
            '(L001) yes is not a valid CORS option'
        ]

        self.assertIsInstance(err_msgs, list)
        self.assertEqual(len(err_msgs), 7)
        for err_msg in err_msgs:
            with self.subTest():
                self.assertIsInstance(err_msg, str)
        self.assertEqual(err_msgs, expected_err_msgs)

    def test_check_file_format_with_correct_format(self):
        correct_format = [
            '## Index',
            '* [A](#a)',
            '* [B](#b)',
            '',
            '### A',
            'API | Description | Auth | HTTPS | CORS |',
            '|---|---|---|---|---|',
            '| [AA](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
            '| [AB](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
            '| [AC](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
            '',
            '### B',
            'API | Description | Auth | HTTPS | CORS |',
            '|---|---|---|---|---|',
            '| [BA](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
            '| [BB](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
            '| [BC](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |'
        ]

        err_msgs = check_file_format(lines=correct_format)

        self.assertIsInstance(err_msgs, list)
        self.assertEqual(len(err_msgs), 0)
        self.assertEqual(err_msgs, [])

    def test_check_file_format_with_category_header_not_added_to_index(self):
        incorrect_format = [
            '## Index',
            '',
            '### A',
            'API | Description | Auth | HTTPS | CORS |',
            '|---|---|---|---|---|',
            '| [AA](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
            '| [AB](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
            '| [AC](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
        ]

        err_msgs = check_file_format(lines=incorrect_format)
        expected_err_msg = '(L003) category header (A) not added to Index section'

        self.assertIsInstance(err_msgs, list)
        self.assertEqual(len(err_msgs), 1)
        err_msg = err_msgs[0]
        self.assertEqual(err_msg, expected_err_msg)

    def test_check_file_format_with_category_without_min_entries(self):
        incorrect_format = [
            '## Index',
            '* [A](#a)',
            '* [B](#b)',
            '',
            '### A',
            'API | Description | Auth | HTTPS | CORS |',
            '|---|---|---|---|---|',
            '| [AA](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
            '',
            '### B',
            'API | Description | Auth | HTTPS | CORS |',
            '|---|---|---|---|---|',
            '| [BA](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
            '| [BB](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
            '| [BC](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |'
        ]

        category_with_err = 'A'
        num_in_category = 1

        err_msgs = check_file_format(lines=incorrect_format)
        expected_err_msg = f'(L005) {category_with_err} category does not have the minimum {min_entries_per_category} entries (only has {num_in_category})'

        self.assertIsInstance(err_msgs, list)
        self.assertEqual(len(err_msgs), 1)
        err_msg = err_msgs[0]
        self.assertEqual(err_msg, expected_err_msg)

    def test_check_file_format_entry_without_all_necessary_columns(self):
        incorrect_format = [
            '## Index',
            '* [A](#a)',
            '',
            '### A',
            'API | Description | Auth | HTTPS | CORS |',
            '|---|---|---|---|---|',
            '| [AA](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
            '| [AB](https://www.ex.com) | Desc | `apiKey` |',  # missing https and cors
            '| [AC](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
        ]

        current_segments_num = 3

        err_msgs = check_file_format(lines=incorrect_format)
        expected_err_msg = f'(L008) entry does not have all the required columns (have {current_segments_num}, need {num_segments})'

        self.assertIsInstance(err_msgs, list)
        self.assertEqual(len(err_msgs), 1)
        err_msg = err_msgs[0]
        self.assertEqual(err_msg, expected_err_msg)

    def test_check_file_format_without_1_space_between_the_segments(self):
        incorrect_format = [
            '## Index',
            '* [A](#a)',
            '',
            '### A',
            'API | Description | Auth | HTTPS | CORS |',
            '|---|---|---|---|---|',
            '| [AA](https://www.ex.com) | Desc |`apiKey`| Yes | Yes |',  # space between segment of auth column missing
            '| [AB](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
            '| [AC](https://www.ex.com) | Desc | `apiKey` | Yes | Yes |',
        ]

        err_msgs = check_file_format(lines=incorrect_format)
        expected_err_msg = f'(L007) each segment must start and end with exactly 1 space'

        self.assertIsInstance(err_msgs, list)
        self.assertEqual(len(err_msgs), 1)
        err_msg = err_msgs[0]
        self.assertEqual(err_msg, expected_err_msg)
