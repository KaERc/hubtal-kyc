"""Indonesia visa sponsorship without Employer of Record. Source: the NON-EOR reference form, plus three deliberate changes (README, "Where I departed from the form")."""
from .spec import Doc, Field, Flow, Section, ch, with_other

PURPOSE = ch('Work', 'Pleasure', 'Retirement', 'Joint Family Member', 'Relocation', ('other', 'Other'))
LENGTH = ch(('lt1', 'Less than 1 year'), ('1-3', '1–3 years'), ('3-5', '3–5 years'), ('gt5', 'More than 5 years'))
WEALTH = ch('Employment', 'Business Ownership', 'Investment', 'Inheritance', ('other', 'Other'))
RECEIVING = ch('Bank Transfer', 'Dividend', 'Third Party Transfer', ('other', 'Other'))
HOUSING = ch('Landed House', 'Apartment', 'Condo', 'Hotel')
TENURE = ch('Daily', 'Monthly', 'Yearly')

EARNS = (('primary_source', 'employment'), ('primary_source', 'business-ownership'))

DECLARATIONS = (
    'All information and documents provided by me in connection with this KYC Assessment and visa sponsorship process are true, accurate, and complete to the best of my knowledge.',
    'I am not involved in any criminal activity and have not been convicted of any criminal offense in any jurisdiction.',
    'I am not currently subject to any investigation, legal proceedings, or regulatory sanctions.',
    'I am not listed on any international sanctions or watchlists, including but not limited to those issued by governmental or international authorities.',
    'The source of my wealth and funds is lawful, legitimate, and not derived from any illegal activities, including but not limited to fraud, corruption, or money laundering.',
    'My intended activities in Indonesia are lawful and consistent with the purpose of the visa being applied for.',
    'I agree to comply with all applicable laws and regulations in Indonesia, including immigration and tax requirements.',
    'I understand that the Company reserves the right to verify any information provided and may request additional documents if necessary.',
    'I acknowledge that any false, misleading, or incomplete information may result in the rejection of my application or termination of services without liability to the Company.',
    'I hereby give my consent for the Company to conduct background checks, including identity verification, sanctions screening, and other due diligence procedures deemed necessary.',
)

FLOW = Flow(
    key='id-non-eor',
    version='2026-10-30',
    country='ID',
    title='Indonesia — visa sponsorship (non-EOR)',
    subject='applicant.full_name',
    sections=(
        Section('applicant', 'Applicant information', (
            Field('full_name', 'Full name (as in passport)'),
            Field('nationality', 'Nationality'),
            Field('passport_number', 'Passport number'),
            Field('passport_expiry', 'Passport expiry date', 'date', rule='future'),
            Field('date_of_birth', 'Date of birth', 'date', rule='past'),
            Field('address', 'Current address / residency', 'textarea'),
            Field('email', 'Email', 'email'),
            Field('phone', 'Phone number', 'tel'),
        )),
        Section('stay', 'Purpose of stay', (
            *with_other(Field('purpose', 'Purpose of stay', 'select', options=PURPOSE)),
            Field('length', 'Intended length of stay', 'select', options=LENGTH),
            Field('activities', 'Activities in Indonesia', 'textarea',
                  help='Describe your activity plan for the next year in one paragraph.'),
            Field('daily_overview', 'Daily activity overview', 'textarea',
                  help='Your daily routine in Indonesia; mention the city or area if you already know it.'),
        )),
        Section('wealth', 'Source of wealth', (
            *with_other(Field('primary_source', 'Primary source of wealth', 'select', options=WEALTH)),
            Field('employer_name', 'Employer / business name', show_if=EARNS),
            Field('position', 'Position / role', show_if=EARNS),
            Field('funds_origin_country', 'Country of origin of funds'),
            Field('yearly_income', 'Estimated yearly income range', help='For example: USD 60,000–80,000.'),
            *with_other(Field('receiving_method', 'Method of receiving funds', 'multiselect',
                              options=RECEIVING, flag_on='third-party-transfer')),
        )),
        Section('stay_address', 'Address in Indonesia', (
            Field('address', 'Residential address in Indonesia', 'textarea'),
            Field('accommodation', 'Type of accommodation', 'select', options=HOUSING),
            Field('tenure', 'Tenure of rent', 'select', options=TENURE),
        )),
        Section('declarations', 'Declaration', (
            *(Field(f'd{i}', text, 'consent') for i, text in enumerate(DECLARATIONS, 1)),
            Field('signer_name', 'Type your full name to sign'),
        ), intro='Each statement must be confirmed. Typing your name below is your signature.'),
    ),
    docs=(
        Doc('passport', 'Passport copy (photo page)', help='Not in the reference form; any visa case needs it.'),
        Doc('lease_or_booking', 'Lease agreement or booking confirmation'),
        Doc('proof_of_funds', 'Evidence of source of wealth', required=False,
            help='For example a payslip, bank statement or company extract.'),
    ),
)
