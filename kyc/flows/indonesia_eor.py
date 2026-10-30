"""Indonesia visa sponsorship through Employer of Record. Source: the EOR reference form, plus the deliberate changes listed in the README."""
from .spec import Doc, Field, Flow, Section, ch, with_other, yes_no

CONTROL = ch('Direct Shareholders', 'Indirect Shareholders', 'Voting Rights', ('other', 'Other'))
REASON = ch('Hiring an Employee in Indonesia', 'Market Expansion', 'Project Based Assignment',
            'Remote Workforce', 'Business Development', ('other', 'Other'))
EXPERIENCE = ch(('lt5', 'Less than 5 years'), ('5-10', '5–10 years'), ('gt10', 'More than 10 years'))
ARRANGEMENT = ch('On-Site', 'Hybrid', 'Remote')

ANY_YES = (('previously_worked', 'yes'), ('held_kitas', 'yes'), ('refused', 'yes'), ('deported', 'yes'))

COMPANY_DECLARATIONS = (
    'All information and documents provided are true, accurate, and complete.',
    'The Company is legally established and authorized to conduct its business.',
    'Neither the Company nor its Ultimate Beneficial Owners are engaged in unlawful activities, including fraud, bribery, corruption, terrorist financing, money laundering, human trafficking, or sanctions evasion.',
    'The Company agrees to comply with all applicable employment, immigration, tax, anti-money laundering (AML), anti-bribery, sanctions, and data protection laws applicable to the Employer of Record engagement.',
    'The Company authorizes EMERHUB to conduct corporate verification, Ultimate Beneficial Owner verification, sanctions screening, adverse media screening, and any other due diligence deemed necessary.',
    'The Company understands that EMERHUB reserves the right to decline or terminate the Employer of Record engagement if any material compliance risk is identified.',
    'The company consent to the collection, processing, and storage of the company and candidate personal data by EMERHUB for employment, immigration, and compliance purposes in accordance with applicable data protection laws.',
)

FLOW = Flow(
    key='id-eor',
    version='2026-10-30',
    country='ID',
    title='Indonesia — visa sponsorship via Employer of Record (EOR)',
    subject='candidate.full_name',
    sections=(
        Section('employer', 'Foreign employer', (
            Field('company_name', 'Registered company name'),
            Field('trading_name', 'Trading name (if different)', required=False),
            Field('registration_number', 'Registration number'),
            Field('incorporation_country', 'Country of incorporation'),
            Field('incorporation_date', 'Date of incorporation', 'date', rule='past'),
            Field('registered_address', 'Registered business address', 'textarea'),
            Field('website', 'Company website', required=False),
            Field('nature_of_business', 'Nature of business'),
            Field('employees', 'Number of employees', 'number', min=1),
            Field('contact_name', 'Contact person'),
            Field('contact_position', 'Position'),
            Field('contact_email', 'Email address', 'email'),
            Field('contact_phone', 'Telephone number', 'tel'),
        ), party='Employer'),
        Section('ubos', 'Ultimate beneficial owners', (
            Field('full_name', 'Full name'),
            Field('nationality', 'Nationality'),
            Field('residence_country', 'Country of residence'),
            Field('ownership_pct', 'Ownership percentage', 'number', min=0, max=100),
            *with_other(Field('control', 'Nature of control', 'multiselect', options=CONTROL)),
        ), party='Employer', repeat=True, intro='Add one entry for each ultimate beneficial owner.'),
        Section('relationship', 'Business relationship', (
            Field('reason', 'Reason for engaging EOR services', 'select', options=REASON),
            Field('explanation', 'Please explain', 'textarea'),
        ), party='Employer'),
        Section('engagement', 'Employee engagement', (
            Field('start_date', 'Expected start date', 'date', rule='future'),
            Field('position', 'Position'),
            Field('manager_name', 'Reporting manager name'),
            Field('work_location', 'Primary work location'),
            Field('work_arrangement', 'Work arrangement', 'select', options=ARRANGEMENT),
            Field('employment_period', 'Expected employment period', help='For example: 24 months.'),
        ), party='Employer'),
        Section('compliance', 'Company compliance questionnaire', (
            yes_no('incorporated', 'Is the company legally incorporated in its jurisdiction?', flag_on='no'),
            yes_no('bankrupt', 'Has the company ever been declared bankrupt or insolvent?', flag_on='yes'),
            yes_no('litigation', 'Is the company currently involved in litigation that may materially affect its business?', flag_on='yes'),
            yes_no('sanctioned', 'Is the company subject to any government sanctions or regulatory restrictions?', flag_on='yes'),
            yes_no('prohibited', 'Is the company engaged in any prohibited or illegal activities?', flag_on='yes'),
        ), party='Employer', intro='Answers that need attention are highlighted for the reviewer.'),
        Section('candidate', 'Foreign employee candidate', (
            Field('full_name', 'Full name (as per passport)'),
            Field('nationality', 'Nationality'),
            Field('passport_number', 'Passport number'),
            Field('passport_expiry', 'Passport expiry date', 'date', rule='future'),
            Field('date_of_birth', 'Date of birth', 'date', rule='past'),
            Field('residence_country', 'Country of residence'),
            Field('address', 'Current residential address', 'textarea'),
            Field('email', 'Email address', 'email'),
            Field('mobile', 'Mobile number', 'tel'),
        ), party='Candidate'),
        Section('background', 'Employment background', (
            Field('experience', 'Years of professional experience', 'select', options=EXPERIENCE),
            Field('latest_position', 'Latest job position'),
            Field('certification', 'Do you hold a relevant certification or expertise?', 'yesno',
                  options=(('yes', 'Yes, I have it'), ('no', "No, I don't"))),
        ), party='Candidate'),
        Section('immigration', 'Immigration assessment', (
            Field('current_status', 'Current immigration status'),
            yes_no('previously_worked', 'Have you previously worked in Indonesia?'),
            yes_no('held_kitas', 'Have you ever held an Indonesian KITAS or work permit?'),
            yes_no('refused', 'Have you ever been refused an Indonesian visa or work permit?', flag_on='yes'),
            yes_no('deported', 'Have you ever been deported or overstayed in Indonesia or another country?', flag_on='yes'),
            Field('details', 'Please provide details', 'textarea', show_if=ANY_YES),
        ), party='Candidate'),
        Section('declarations', 'Company declaration and authorized representative', (
            *(Field(f'd{i}', text, 'consent') for i, text in enumerate(COMPANY_DECLARATIONS, 1)),
            Field('signer_name', 'Authorized representative — name'),
            Field('signer_position', 'Authorized representative — position'),
        ), party='Employer', intro='Each statement must be confirmed. Typing the name below is the signature.'),
        Section('candidate_consent', 'Candidate consent', (
            Field('d1', 'I confirm that the information about me in this form is true and complete, and I consent to identity verification, '
                        'sanctions screening, background checks and the processing of my personal data for employment, immigration '
                        'and compliance purposes.', 'consent'),
            Field('signer_name', 'Type your full name to sign'),
        ), party='Candidate', intro='Added to the reference form, which only had the company consent on the candidate’s behalf. Needs legal review.'),
    ),
    docs=(
        Doc('company_registration', 'Company registration certificate or registry extract'),
        Doc('ubo_ids', 'ID or passport copy of each beneficial owner'),
        Doc('candidate_passport', 'Candidate passport copy (photo page)'),
        Doc('candidate_cv', 'Candidate CV', required=False),
        Doc('certificates', 'Certification evidence', show_if=(('background.certification', 'yes'),)),
    ),
)
