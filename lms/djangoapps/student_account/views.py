# -*- coding: utf-8 -*-
""" Views for a student's account information. """

import json
import logging
from datetime import datetime

import urlparse
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import redirect
from django.utils.translation import ugettext as _
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django_countries import countries
import third_party_auth

from datetime import date
import commands
from django.views.decorators.csrf import csrf_exempt
from edx_ace import ace
from edx_ace.recipient import Recipient
from edxmako.shortcuts import render_to_response
from lms.djangoapps.commerce.models import CommerceConfiguration
from lms.djangoapps.commerce.utils import EcommerceService
from openedx.core.djangoapps.ace_common.template_context import get_base_template_context
from openedx.core.djangoapps.commerce.utils import ecommerce_api_client
from openedx.core.djangoapps.external_auth.login_and_register import login as external_auth_login
from openedx.core.djangoapps.external_auth.login_and_register import register as external_auth_register
from openedx.core.djangoapps.lang_pref.api import all_languages, released_languages
from openedx.core.djangoapps.programs.models import ProgramsApiConfig
from openedx.core.djangoapps.site_configuration import helpers as configuration_helpers
from openedx.core.djangoapps.theming.helpers import is_request_in_themed_site, get_current_site
from openedx.core.djangoapps.user_api.accounts.api import request_password_change
from openedx.core.djangoapps.user_api.api import (
    RegistrationFormFactory,
    get_login_session_form,
    get_password_reset_form
)
from openedx.core.djangoapps.user_api.errors import (
    UserNotFound,
    UserAPIInternalError
)
from openedx.core.lib.edx_api_utils import get_edx_api_data
from openedx.core.lib.time_zone_utils import TIME_ZONE_CHOICES
from openedx.features.enterprise_support.api import enterprise_customer_for_request, get_enterprise_customer_for_learner
from openedx.features.enterprise_support.utils import (
    handle_enterprise_cookies_for_logistration,
    update_logistration_context_for_enterprise,
    update_account_settings_context_for_enterprise,
)
from student.helpers import destroy_oauth_tokens, get_next_url_for_login_page
from student.message_types import PasswordReset
from student.models import UserProfile
from student.views import register_user as old_register_view, signin_user as old_login_view
from third_party_auth import pipeline
from third_party_auth.decorators import xframe_allow_whitelisted
from util.bad_request_rate_limiter import BadRequestRateLimiter
from util.date_utils import strftime_localized
from django.db import connections
import ast
import urllib
from openedx.core.djangoapps.user_api.accounts.api import check_account_exists

AUDIT_LOG = logging.getLogger("audit")
log = logging.getLogger(__name__)
User = get_user_model()  # pylint:disable=invalid-name

@require_http_methods(['GET'])
@ensure_csrf_cookie
def registration_gubn(request):
    return render_to_response('student_account/registration_gubn.html')


@ensure_csrf_cookie
def agree(request):
    print 'request.method = ', request.method
    print "request.POST['division'] = ", request.POST['division']

    if request.method == 'POST' and request.POST['division']:
        request.session['division'] = request.POST['division']
        print "STEP1 : request.session['division'] = ", request.session['division']

        context = {
            'division': request.session['division'],
        }

        return render_to_response('student_account/agree.html', context)
    else:
        return render_to_response('student_account/registration_gubn.html')


@ensure_csrf_cookie
def agree_done(request):
    # print 'request.is_ajax = ', request.is_ajax
    # print 'request.method = ', request.method
    # print "request.POST['division'] = ", request.POST['agreeYN']

    data = {}

    if request.method == 'POST' and request.POST['agreeYN'] and request.POST['agreeYN'] == 'Y':
        # print "STEP2 :  request.session['division'] = ", request.session['division']
        # print "STEP2 :  request.session['agreeYN'] = ", request.POST['agreeYN']
        request.session['agreeYN'] = request.POST['agreeYN']

        if request.POST['agreeYN'] == 'Y':
            data['agreeYN'] = request.session['agreeYN']
            data['division'] = request.session['division']

        if 'private_info_use_yn' in request.session and 'event_join_yn' in request.session:
            del request.session['private_info_use_yn']
            del request.session['event_join_yn']

        # 개인정보 수집 및 이용 동의 홍보/설문 관련 정보 수진 동의값 저장
        request.session['private_info_use_yn'] = request.POST['private_info_use_yn']
        request.session['event_join_yn'] = request.POST['event_join_yn']

        print "request.session['private_info_use_yn']",request.session['private_info_use_yn']
        print "request.session['event_join_yn']",request.session['event_join_yn']
    else:
        data['agreeYN'] = request.POST['agreeYN']

    print 'data = ', data

    return HttpResponse(json.dumps(data))


@csrf_exempt
def parent_agree(request):
    ## IPIN info

    print 'ipin module called1'

    sSiteCode = 'M231'
    sSitePw = '76421752'
    sModulePath = '/edx/app/edxapp/IPINClient'
    sCPRequest = commands.getoutput(sModulePath + ' SEQ ' + sSiteCode)
    sReturnURL = 'https://www.kmooc.kr/parent_agree_done'
    sEncData = commands.getoutput(sModulePath + ' REQ ' + sSiteCode + ' ' + sSitePw + ' ' + sCPRequest + ' ' + sReturnURL)

    print '===================================================='
    print '1 = ', sModulePath + ' SEQ ' + sSiteCode
    print '===================================================='
    print '3 = ', sCPRequest
    print '===================================================='
    print '4 = ', sModulePath + ' REQ ' + sSiteCode + ' ' + sSitePw + ' ' + sCPRequest + ' ' + sReturnURL
    print '===================================================='
    print '5 = ', sEncData
    print '===================================================='

    if sEncData == -9:
        sRtnMsg = '입력값 오류 : 암호화 처리시 필요한 파라미터값의 정보를 정확하게 입력해 주시기 바랍니다.'
    else:
        sRtnMsg = sEncData + ' 변수에 암호화 데이터가 확인되면 정상 정상이 아닌경우 리턴코드 확인 후 NICE평가정보 개발 담당자에게 문의해 주세요.'

    print 'sRtnMsg = ', sRtnMsg

    context = {
        'sEncData': sEncData,
    }

    return render_to_response('student_account/parent_agree.html', context)


@csrf_exempt
def parent_agree_done(request):
    sSiteCode = 'M231'
    sSitePw = '76421752'
    sModulePath = '/edx/app/edxapp/IPINClient'
    sEncData = request.POST['enc_data']

    sDecData = commands.getoutput(sModulePath + ' RES ' + sSiteCode + ' ' + sSitePw + ' ' + sEncData)

    print 'sDecData', sDecData

    if sDecData:
        val = sDecData.split('^')
        if val[6] and len(val[6]) == 8:
            context = {
                'isAuth': 'succ',
                'age': int(date.today().year) - int(val[6][:4]),
            }

            if int(date.today().year) - int(val[6][:4]) < 20:
                pass
            else:
                request.session['auth'] = 'Y'
    else:
        context = {
            'isAuth': 'fail',
            'age': 0,
        }

    print 'context > ', context

    return render_to_response('student_account/parent_agree_done.html', context)



@require_http_methods(['GET'])
@ensure_csrf_cookie
@xframe_allow_whitelisted
def login_and_registration_form(request, initial_mode="login"):
    """Render the combined login/registration form, defaulting to login

    This relies on the JS to asynchronously load the actual form from
    the user_api.

    Keyword Args:
        initial_mode (string): Either "login" or "register".

    """
    # Determine the URL to redirect to following login/registration/third_party_auth
    redirect_to = get_next_url_for_login_page(request)
    provider_info = _third_party_auth_context(request, redirect_to)

    # print 'currentProvider:', provider_info['currentProvider']
    # add kocw logic
    division = None

    # 로그인중이거나 oauth2 인증이 되어있으면 화면전환을 건너뜀
    if initial_mode == "login" or provider_info['currentProvider']:
        print 'login_and_registration_form type 1'
        pass
    elif 'errorMessage' in provider_info and provider_info['errorMessage'] is not None:
        print 'login_and_registration_form type 2'
        pass
    elif 'division' in request.session and 'agreeYN' in request.session and 'auth' in request.session:
        print 'login_and_registration_form type 3'
        division = request.session['division']
        # del request.session['division']
        # del request.session['agreeYN']
        # del request.session['auth']
    elif 'division' in request.session and 'agreeYN' in request.session:
        print 'login_and_registration_form type 4'
        division = request.session['division']
        if request.session['division'] == 'N':
            return render_to_response('student_account/registration_gubn.html')
        # del request.session['division']
        # del request.session['agreeYN']

    else:
        print 'login_and_registration_form type 5'
        return render_to_response('student_account/registration_gubn.html')

    if 'division' in request.session:
        division = request.session.get('division')

    print 'division!!=',division
    # If we're already logged in, redirect to the dashboard
    if request.user.is_authenticated:
        return redirect(redirect_to)
    # print 'division = ', division
    # Retrieve the form descriptions from the user API
    form_descriptions = _get_form_descriptions(request)

    # Our ?next= URL may itself contain a parameter 'tpa_hint=x' that we need to check.
    # If present, we display a login page focused on third-party auth with that provider.
    third_party_auth_hint = None
    if '?' in redirect_to:
        try:
            next_args = urlparse.parse_qs(urlparse.urlparse(redirect_to).query)
            provider_id = next_args['tpa_hint'][0]
            tpa_hint_provider = third_party_auth.provider.Registry.get(provider_id=provider_id)
            if tpa_hint_provider:
                if tpa_hint_provider.skip_hinted_login_dialog:
                    # Forward the user directly to the provider's login URL when the provider is configured
                    # to skip the dialog.
                    if initial_mode == "register":
                        print 'student_views_login_register   pass1'
                        auth_entry = pipeline.AUTH_ENTRY_REGISTER
                    else:
                        auth_entry = pipeline.AUTH_ENTRY_LOGIN
                    return redirect(
                        pipeline.get_login_url(provider_id, auth_entry, redirect_url=redirect_to)
                    )
                third_party_auth_hint = provider_id
                initial_mode = "hinted_login"
        except (KeyError, ValueError, IndexError) as ex:
            log.error("Unknown tpa_hint provider: %s", ex)

    # If this is a themed site, revert to the old login/registration pages.
    # We need to do this for now to support existing themes.
    # Themed sites can use the new logistration page by setting
    # 'ENABLE_COMBINED_LOGIN_REGISTRATION' in their
    # configuration settings.
    # microsite not 처리
    if not is_request_in_themed_site() and not configuration_helpers.get_value('ENABLE_COMBINED_LOGIN_REGISTRATION', False):
        if initial_mode == "login":
            return old_login_view(request)
        elif initial_mode == "register":
            print 'student_views_login_register   pass3'
            return old_register_view(request)

    # Allow external auth to intercept and handle the request
    ext_auth_response = _external_auth_intercept(request, initial_mode)
    if ext_auth_response is not None:
        return ext_auth_response

    # Account activation message
    account_activation_messages = [
        {
            'message': message.message, 'tags': message.tags
        } for message in messages.get_messages(request) if 'account-activation' in message.tags
    ]

    # Otherwise, render the combined login/registration page
    context = {
        'data': {
            'login_redirect_url': redirect_to,
            'initial_mode': initial_mode,
            'third_party_auth': _third_party_auth_context(request, redirect_to, third_party_auth_hint),
            'third_party_auth_hint': third_party_auth_hint or '',
            'platform_name': configuration_helpers.get_value('PLATFORM_NAME', settings.PLATFORM_NAME),
            'support_link': configuration_helpers.get_value('SUPPORT_SITE_LINK', settings.SUPPORT_SITE_LINK),
            'password_reset_support_link': configuration_helpers.get_value(
                'PASSWORD_RESET_SUPPORT_LINK', settings.PASSWORD_RESET_SUPPORT_LINK
            ) or settings.SUPPORT_SITE_LINK,
            'account_activation_messages': account_activation_messages,

            # Include form descriptions retrieved from the user API.
            # We could have the JS client make these requests directly,
            # but we include them in the initial page load to avoid
            # the additional round-trip to the server.
            'login_form_desc': json.loads(form_descriptions['login']),
            'registration_form_desc': json.loads(form_descriptions['registration']),
            'password_reset_form_desc': json.loads(form_descriptions['password_reset']),
            'account_creation_allowed': configuration_helpers.get_value(
                'ALLOW_PUBLIC_ACCOUNT_CREATION', settings.FEATURES.get('ALLOW_PUBLIC_ACCOUNT_CREATION', True))
        },
        'login_redirect_url': redirect_to,  # This gets added to the query string of the "Sign In" button in header
        'responsive': True,
        'allow_iframing': True,
        'disable_courseware_js': True,
        'combined_login_and_register': True,
        'disable_footer': not configuration_helpers.get_value(
            'ENABLE_COMBINED_LOGIN_REGISTRATION_FOOTER',
            settings.FEATURES['ENABLE_COMBINED_LOGIN_REGISTRATION_FOOTER']
        ),
        'disable_footer': True,
        'division': division,
    }

    enterprise_customer = enterprise_customer_for_request(request)
    update_logistration_context_for_enterprise(request, context, enterprise_customer)

    response = render_to_response('student_account/login_and_register.html', context)
    handle_enterprise_cookies_for_logistration(request, response, context)
    print 'student_views_login_register   pass2'
    return response


@require_http_methods(['POST'])
def password_change_request_handler(request):
    """Handle password change requests originating from the account page.

    Uses the Account API to email the user a link to the password reset page.

    Note:
        The next step in the password reset process (confirmation) is currently handled
        by student.views.password_reset_confirm_wrapper, a custom wrapper around Django's
        password reset confirmation view.

    Args:
        request (HttpRequest)

    Returns:
        HttpResponse: 200 if the email was sent successfully
        HttpResponse: 400 if there is no 'email' POST parameter
        HttpResponse: 403 if the client has been rate limited
        HttpResponse: 405 if using an unsupported HTTP method

    Example usage:

        POST /account/password

    """

    limiter = BadRequestRateLimiter()
    if limiter.is_rate_limit_exceeded(request):
        AUDIT_LOG.warning("Password reset rate limit exceeded")
        return HttpResponseForbidden()

    user = request.user
    # Prefer logged-in user's email
    email = user.email if user.is_authenticated else request.POST.get('email')

    if email:
        try:
            request_password_change(email, request.is_secure())
            user = user if user.is_authenticated else User.objects.get(email=email)
            destroy_oauth_tokens(user)
        except UserNotFound:
            AUDIT_LOG.info("Invalid password reset attempt")
            # Increment the rate limit counter
            limiter.tick_bad_request_counter(request)

            # If enabled, send an email saying that a password reset was attempted, but that there is
            # no user associated with the email
            if configuration_helpers.get_value('ENABLE_PASSWORD_RESET_FAILURE_EMAIL',
                                               settings.FEATURES['ENABLE_PASSWORD_RESET_FAILURE_EMAIL']):

                site = get_current_site()
                message_context = get_base_template_context(site)

                message_context.update({
                    'failed': True,
                    'request': request,  # Used by google_analytics_tracking_pixel
                    'email_address': email,
                })

                msg = PasswordReset().personalize(
                    recipient=Recipient(username='', email_address=email),
                    language=settings.LANGUAGE_CODE,
                    user_context=message_context,
                )

                ace.send(msg)
        except UserAPIInternalError as err:
            log.exception('Error occured during password change for user {email}: {error}'
                          .format(email=email, error=err))
            return HttpResponse(_("Some error occured during password change. Please try again"), status=500)

        return HttpResponse(status=200)
    else:
        return HttpResponseBadRequest(_("No email address provided."))


def _third_party_auth_context(request, redirect_to, tpa_hint=None):
    """Context for third party auth providers and the currently running pipeline.

    Arguments:
        request (HttpRequest): The request, used to determine if a pipeline
            is currently running.
        redirect_to: The URL to send the user to following successful
            authentication.
        tpa_hint (string): An override flag that will return a matching provider
            as long as its configuration has been enabled

    Returns:
        dict

    """
    context = {
        "currentProvider": None,
        "providers": [],
        "secondaryProviders": [],
        "finishAuthUrl": None,
        "errorMessage": None,
        "registerFormSubmitButtonText": _("Create Account"),
        "syncLearnerProfileData": False,
        "pipeline_user_details": {}
    }

    if third_party_auth.is_enabled():
        for enabled in third_party_auth.provider.Registry.displayed_for_login(tpa_hint=tpa_hint):
            info = {
                "id": enabled.provider_id,
                "name": enabled.name,
                "iconClass": enabled.icon_class or None,
                "iconImage": enabled.icon_image.url if enabled.icon_image else None,
                "loginUrl": pipeline.get_login_url(
                    enabled.provider_id,
                    pipeline.AUTH_ENTRY_LOGIN,
                    redirect_url=redirect_to,
                ),
                "registerUrl": pipeline.get_login_url(
                    enabled.provider_id,
                    pipeline.AUTH_ENTRY_REGISTER,
                    redirect_url=redirect_to,
                ),
            }
            context["providers" if not enabled.secondary else "secondaryProviders"].append(info)

        running_pipeline = pipeline.get(request)
        if running_pipeline is not None:
            current_provider = third_party_auth.provider.Registry.get_from_pipeline(running_pipeline)
            user_details = running_pipeline['kwargs']['details']
            if user_details:
                context['pipeline_user_details'] = user_details

            if current_provider is not None:
                context["currentProvider"] = current_provider.name
                context["finishAuthUrl"] = pipeline.get_complete_url(current_provider.backend_name)
                context["syncLearnerProfileData"] = current_provider.sync_learner_profile_data

                if current_provider.skip_registration_form:
                    # As a reliable way of "skipping" the registration form, we just submit it automatically
                    context["autoSubmitRegForm"] = True

        # Check for any error messages we may want to display:
        for msg in messages.get_messages(request):
            if msg.extra_tags.split()[0] == "social-auth":
                # msg may or may not be translated. Try translating [again] in case we are able to:
                context['errorMessage'] = _(unicode(msg))  # pylint: disable=translation-of-non-string
                break

    return context


def _get_form_descriptions(request):
    """Retrieve form descriptions from the user API.

    Arguments:
        request (HttpRequest): The original request, used to retrieve session info.

    Returns:
        dict: Keys are 'login', 'registration', and 'password_reset';
            values are the JSON-serialized form descriptions.

    """

    return {
        'password_reset': get_password_reset_form().to_json(),
        'login': get_login_session_form(request).to_json(),
        'registration': RegistrationFormFactory().get_registration_form(request).to_json()
    }


def _get_extended_profile_fields():
    """Retrieve the extended profile fields from site configuration to be shown on the
       Account Settings page

    Returns:
        A list of dicts. Each dict corresponds to a single field. The keys per field are:
            "field_name"  : name of the field stored in user_profile.meta
            "field_label" : The label of the field.
            "field_type"  : TextField or ListField
            "field_options": a list of tuples for options in the dropdown in case of ListField
    """

    extended_profile_fields = []
    fields_already_showing = ['username', 'name', 'email', 'pref-lang', 'country', 'time_zone', 'level_of_education',
                              'gender', 'year_of_birth', 'language_proficiencies', 'social_links']

    field_labels_map = {
        "first_name": _(u"First Name"),
        "last_name": _(u"Last Name"),
        "city": _(u"City"),
        "state": _(u"State/Province/Region"),
        "company": _(u"Company"),
        "title": _(u"Title"),
        "job_title": _(u"Job Title"),
        "mailing_address": _(u"Mailing address"),
        "goals": _(u"Tell us why you're interested in {platform_name}").format(
            platform_name=configuration_helpers.get_value("PLATFORM_NAME", settings.PLATFORM_NAME)
        ),
        "profession": _(u"Profession"),
        "specialty": _(u"Specialty")
    }

    extended_profile_field_names = configuration_helpers.get_value('extended_profile_fields', [])
    for field_to_exclude in fields_already_showing:
        if field_to_exclude in extended_profile_field_names:
            extended_profile_field_names.remove(field_to_exclude)  # pylint: disable=no-member

    extended_profile_field_options = configuration_helpers.get_value('EXTRA_FIELD_OPTIONS', [])
    extended_profile_field_option_tuples = {}
    for field in extended_profile_field_options.keys():
        field_options = extended_profile_field_options[field]
        extended_profile_field_option_tuples[field] = [(option.lower(), option) for option in field_options]

    for field in extended_profile_field_names:
        field_dict = {
            "field_name": field,
            "field_label": field_labels_map.get(field, field),
        }

        field_options = extended_profile_field_option_tuples.get(field)
        if field_options:
            field_dict["field_type"] = "ListField"
            field_dict["field_options"] = field_options
        else:
            field_dict["field_type"] = "TextField"
        extended_profile_fields.append(field_dict)

    return extended_profile_fields


def _external_auth_intercept(request, mode):
    """Allow external auth to intercept a login/registration request.

    Arguments:
        request (Request): The original request.
        mode (str): Either "login" or "register"

    Returns:
        Response or None

    """
    if mode == "login":
        return external_auth_login(request)
    elif mode == "register":
        return external_auth_register(request)


def get_user_orders(user):
    """Given a user, get the detail of all the orders from the Ecommerce service.

    Args:
        user (User): The user to authenticate as when requesting ecommerce.

    Returns:
        list of dict, representing orders returned by the Ecommerce service.
    """
    no_data = []
    user_orders = []
    commerce_configuration = CommerceConfiguration.current()
    user_query = {'username': user.username}

    use_cache = commerce_configuration.is_cache_enabled
    cache_key = commerce_configuration.CACHE_KEY + '.' + str(user.id) if use_cache else None
    api = ecommerce_api_client(user)
    commerce_user_orders = get_edx_api_data(
        commerce_configuration, 'orders', api=api, querystring=user_query, cache_key=cache_key
    )

    for order in commerce_user_orders:
        if order['status'].lower() == 'complete':
            date_placed = datetime.strptime(order['date_placed'], "%Y-%m-%dT%H:%M:%SZ")
            order_data = {
                'number': order['number'],
                'price': order['total_excl_tax'],
                'order_date': strftime_localized(date_placed, 'SHORT_DATE'),
                'receipt_url': EcommerceService().get_receipt_page_url(order['number']),
                'lines': order['lines'],
            }
            user_orders.append(order_data)

    return user_orders


@login_required
@require_http_methods(['GET'])
def account_settings(request):
    """Render the current user's account settings page.

    Args:
        request (HttpRequest)

    Returns:
        HttpResponse: 200 if the page was sent successfully
        HttpResponse: 302 if not logged in (redirect to login page)
        HttpResponse: 405 if using an unsupported HTTP method

    Example usage:

        GET /account/settings

    """
    context = account_settings_context(request)
    return render_to_response('student_account/account_settings.html', context)


@login_required
@require_http_methods(['GET'])
def finish_auth(request):  # pylint: disable=unused-argument
    """ Following logistration (1st or 3rd party), handle any special query string params.

    See FinishAuthView.js for details on the query string params.

    e.g. auto-enroll the user in a course, set email opt-in preference.

    This view just displays a "Please wait" message while AJAX calls are made to enroll the
    user in the course etc. This view is only used if a parameter like "course_id" is present
    during login/registration/third_party_auth. Otherwise, there is no need for it.

    Ideally this view will finish and redirect to the next step before the user even sees it.

    Args:
        request (HttpRequest)

    Returns:
        HttpResponse: 200 if the page was sent successfully
        HttpResponse: 302 if not logged in (redirect to login page)
        HttpResponse: 405 if using an unsupported HTTP method

    Example usage:

        GET /account/finish_auth/?course_id=course-v1:blah&enrollment_action=enroll

    """
    return render_to_response('student_account/finish_auth.html', {
        'disable_courseware_js': True,
        'disable_footer': True,
    })


def account_settings_context(request):
    print 'account_settings_context!!!'
    """ Context for the account settings page.

    Args:
        request: The request object.

    Returns:
        dict

    """
    # -------------------- nice core -------------------- #
    nice_sitecode       = 'AD521'                      # NICE로부터 부여받은 사이트 코드
    nice_sitepasswd     = 'z0lWlstxnw0u'               # NICE로부터 부여받은 사이트 패스워드
    nice_cb_encode_path = '/edx/app/edxapp/edx-platform/CPClient'

    nice_authtype       = ''                           # 없으면 기본 선택화면, X: 공인인증서, M: 핸드폰, C: 카드
    nice_popgubun       = 'N'                          # Y : 취소버튼 있음 / N : 취소버튼 없음
    nice_customize      = ''                           # 없으면 기본 웹페이지 / Mobile : 모바일페이지
    nice_gender         = ''                           # 없으면 기본 선택화면, 0: 여자, 1: 남자
    nice_reqseq         = 'REQ0000000001'              # 요청 번호, 이는 성공/실패후에 같은 값으로 되돌려주게 되므로
                                                       # 업체에서 적절하게 변경하여 쓰거나, 아래와 같이 생성한다.
    lms_base = settings.ENV_TOKENS.get('LMS_BASE')

    nice_returnurl      = "http://{lms_base}/nicecheckplus".format(lms_base=lms_base)        # 성공시 이동될 URL
    nice_errorurl       = "http://{lms_base}/nicecheckplus_error".format(lms_base=lms_base)  # 실패시 이동될 URL
    nice_returnMsg      = ''

    plaindata = '7:REQ_SEQ{0}:{1}8:SITECODE{2}:{3}9:AUTH_TYPE{4}:{5}7:RTN_URL{6}:{7}7:ERR_URL{8}:{9}11:POPUP_GUBUN{10}:{11}9:CUSTOMIZE{12}:{13}6:GENDER{14}:{15}'\
                .format(len(nice_reqseq),nice_reqseq,
                        len(nice_sitecode),nice_sitecode,
                        len(nice_authtype),nice_authtype,
                        len(nice_returnurl),nice_returnurl,
                        len(nice_errorurl),nice_errorurl,
                        len(nice_popgubun),nice_popgubun,
                        len(nice_customize),nice_customize,
                        len(nice_gender),nice_gender )

    nice_command = '{0} ENC {1} {2} {3}'.format(nice_cb_encode_path, nice_sitecode, nice_sitepasswd, plaindata)
    enc_data = commands.getoutput(nice_command)

    if enc_data == -1 :
        nice_returnMsg = "암/복호화 시스템 오류입니다."
        enc_data = ""
    elif enc_data== -2 :
        nice_returnMsg = "암호화 처리 오류입니다."
        enc_data = ""
    elif enc_data== -3 :
        nice_returnMsg = "암호화 데이터 오류 입니다."
        enc_data = ""
    elif enc_data== -9 :
        nice_returnMsg = "입력값 오류 입니다."
        enc_data = ""

    # ----- DEBUG ----- #
    """
    print "nice_sitecode = {}".format(nice_sitecode)
    print "nice_sitepasswd = {}".format(nice_sitepasswd)
    print "nice_cb_encode_path = {}".format(nice_cb_encode_path)
    print "nice_authtype = {}".format(nice_authtype)
    print "nice_popgubun = {}".format(nice_popgubun)
    print "nice_customize = {}".format(nice_customize)
    print "nice_gender = {}".format(nice_gender)
    print "nice_reqseq = {}".format(nice_reqseq)
    print "nice_returnurl = {}".format(nice_returnurl)
    print "nice_errorurl = {}".format(nice_errorurl)
    print "plaindata = {}".format(plaindata)
    print "enc_data = {}".format(enc_data)
    """
    # ----- DEBUG ----- #
    # -------------------- nice core -------------------- #

    # -------------------- nice check -------------------- #
    try:
        edx_user_email = request.user.email
    except BaseException:
        edx_user_email = ''

    nice_info = None

    with connections['default'].cursor() as cur:
        try:
            query = """
                SELECT b.name, b.gender, b.year_of_birth, a.plain_data
                  FROM auth_user_nicecheck AS a
                       LEFT JOIN auth_userprofile AS b ON a.user_id = b.user_id
                       JOIN auth_user AS c ON b.user_id = c.id
                 WHERE c.email = '{0}'
            """.format(edx_user_email)
            cur.execute(query)
            table = cur.fetchone()
            #user_name = table[0]
            user_gender = table[1]
            user_birthday = table[2]
            nice_info = table[3]
            nice_check = 'yes'
        except BaseException:
            #user_name = None
            user_gender = None
            user_birthday = None
            nice_check = 'no'
    # -------------------- nice check -------------------- #

    if nice_info != None:
        nice_dict = ast.literal_eval(nice_info)
        user_name = nice_dict['UTF8_NAME']
        user_name = urllib.unquote(user_name).decode('utf8')
    else:
        user_name = ''
    user = request.user

    year_of_birth_options = [(unicode(year), unicode(year)) for year in UserProfile.VALID_YEARS]
    try:
        user_orders = get_user_orders(user)
    except:  # pylint: disable=bare-except
        log.exception('Error fetching order history from Otto.')
        # Return empty order list as account settings page expect a list and
        # it will be broken if exception raised
        user_orders = []

    countries_list = list(countries)
    countries_list.insert(0, (u'KR', u'South Korea'))
    print 'countries_list',countries_list
    context = {
        'user_gender': user_gender,  # context -> nice data
        'user_birthday': user_birthday,  # context -> nice data
        'user_name': user_name,  # context -> nice data
        'nice_check': nice_check,  # context -> nice data
        'enc_data': enc_data,  # context -> nice data
        'auth': {},
        'duplicate_provider': None,
        'nav_hidden': True,
        'fields': {
            'country': {
                'options': countries_list,
            }, 'gender': {
                'options': [(choice[0], _(choice[1])) for choice in UserProfile.GENDER_CHOICES],  # pylint: disable=translation-of-non-string
            }, 'language': {
                'options': released_languages(),
            }, 'level_of_education': {
                'options': [(choice[0], _(choice[1])) for choice in UserProfile.LEVEL_OF_EDUCATION_CHOICES],  # pylint: disable=translation-of-non-string
            }, 'password': {
                'url': reverse('password_reset'),
            }, 'year_of_birth': {
                'options': year_of_birth_options,
            }, 'preferred_language': {
                'options': all_languages(),
            }, 'time_zone': {
                'options': TIME_ZONE_CHOICES,
            }
        },
        'platform_name': configuration_helpers.get_value('PLATFORM_NAME', settings.PLATFORM_NAME),
        'password_reset_support_link': configuration_helpers.get_value(
            'PASSWORD_RESET_SUPPORT_LINK', settings.PASSWORD_RESET_SUPPORT_LINK
        ) or settings.SUPPORT_SITE_LINK,
        'user_accounts_api_url': reverse("accounts_api", kwargs={'username': user.username}),
        'user_preferences_api_url': reverse('preferences_api', kwargs={'username': user.username}),
        'disable_courseware_js': True,
        'show_program_listing': ProgramsApiConfig.is_enabled(),
        'show_dashboard_tabs': True,
        'order_history': user_orders,
        'enable_account_deletion': configuration_helpers.get_value(
            'ENABLE_ACCOUNT_DELETION', settings.FEATURES.get('ENABLE_ACCOUNT_DELETION', False)
        ),
        'extended_profile_fields': _get_extended_profile_fields(),
    }

    enterprise_customer = get_enterprise_customer_for_learner(site=request.site, user=request.user)
    update_account_settings_context_for_enterprise(context, enterprise_customer)

    if third_party_auth.is_enabled():
        # If the account on the third party provider is already connected with another edX account,
        # we display a message to the user.
        context['duplicate_provider'] = pipeline.get_duplicate_provider(messages.get_messages(request))

        auth_states = pipeline.get_provider_user_states(user)

        context['auth']['providers'] = [{
            'id': state.provider.provider_id,
            'name': state.provider.name,  # The name of the provider e.g. Facebook
            'connected': state.has_account,  # Whether the user's edX account is connected with the provider.
            # If the user is not connected, they should be directed to this page to authenticate
            # with the particular provider, as long as the provider supports initiating a login.
            'connect_url': pipeline.get_login_url(
                state.provider.provider_id,
                pipeline.AUTH_ENTRY_ACCOUNT_SETTINGS,
                # The url the user should be directed to after the auth process has completed.
                redirect_url=reverse('account_settings'),
            ),
            'accepts_logins': state.provider.accepts_logins,
            # If the user is connected, sending a POST request to this url removes the connection
            # information for this provider from their edX account.
            'disconnect_url': pipeline.get_disconnect_url(state.provider.provider_id, state.association_id),
            # We only want to include providers if they are either currently available to be logged
            # in with, or if the user is already authenticated with them.
        } for state in auth_states if state.provider.display_for_login or state.has_account]

    return context
