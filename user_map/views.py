# coding=utf-8
"""Views of the apps."""
from django.shortcuts import render, render_to_response
from django.http import HttpResponse, HttpResponseRedirect
from django.template import RequestContext, loader, Context
from django.forms.util import ErrorList
from django.forms.forms import NON_FIELD_ERRORS
from django.core.urlresolvers import reverse
from django.core.mail import send_mail
from django.contrib import messages
from django.contrib.auth import (
    login as django_login,
    authenticate,
    logout as django_logout)
from django.contrib.auth.views import (
    password_reset as django_password_reset,
    password_reset_done as django_password_reset_done,
    password_reset_confirm as django_password_reset_confirm,
    password_reset_complete as django_password_reset_complete)
from django.contrib.auth.decorators import login_required
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes
from django.contrib.sites.models import get_current_site

from user_map.forms import (
    UserForm,
    LoginForm,
    BasicInformationForm,
    PasswordForm,
    CustomPasswordResetForm,
    CustomSetPasswordForm)
from user_map.models import User
from user_map.app_settings import (
    PROJECT_NAME, USER_ICONS, DEFAULT_FROM_MAIL, LEAFLET_TILES)
from user_map.utilities.decorators import login_forbidden


def index(request):
    """Index page of user map.

    :param request: A django request object.
    :type request: request

    :returns: Response will be a nice looking map page.
    :rtype: HttpResponse
    """
    information_modal = loader.render_to_string(
        'user_map/information_modal.html')
    data_privacy_content = loader.render_to_string('user_map/data_privacy.html')
    user_menu = dict(
        add_user=True,
        download=True,
        reminder=True
    )
    user_menu_button = loader.render_to_string(
        'user_map/user_menu_button.html',
        dictionary=user_menu
    )
    legend_template = loader.get_template('user_map/legend.html')
    legend_context = Context({'user_icons': USER_ICONS})
    legend = legend_template.render(legend_context)

    leaflet_tiles = dict(
        url=LEAFLET_TILES[1],
        attribution=LEAFLET_TILES[2]
    )
    context = {
        'data_privacy_content': data_privacy_content,
        'information_modal': information_modal,
        'user_menu': user_menu,
        'user_menu_button': user_menu_button,
        'user_icons': USER_ICONS,
        'legend': legend,
        'leaflet_tiles': leaflet_tiles
    }
    return render(request, 'user_map/index.html', context)


def get_users(request):
    """Return a json document of users with given role.

    This will only fetch users who have approved by email and still active.

    :param request: A django request object.
    :type request: request
    """
    # Get data:
    user_role = int(request.GET['user_role'])

    # Get user
    users = User.objects.filter(
        role=user_role,
        is_confirmed=True,
        is_active=True)
    json_users_template = loader.get_template('user_map/users.json')
    context = Context({'users': users})
    json_users = json_users_template.render(context)

    users_json = (
        '{'
        ' "users": %s'
        '}' % json_users
    )
    # Return Response
    return HttpResponse(users_json, mimetype='application/json')


@login_forbidden
def register(request):
    """User registration view.

    :param request: A django request object.
    :type request: request
    """
    if request.method == 'POST':
        form = UserForm(data=request.POST)
        if form.is_valid():
            user = form.save()

            current_site = get_current_site(request)
            site_name = current_site.name
            domain = current_site.domain
            context = {
                'project_name': PROJECT_NAME,
                'protocol': 'http',
                'domain': domain,
                'site_name': site_name,
                'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                'user': user,
                'key': user.key
            }
            email = loader.render_to_string(
                'user_map/account/registration_confirmation_email.html',
                context)

            subject = '%s User Registration' % PROJECT_NAME
            sender = '%s - No Reply <%s>' % (PROJECT_NAME, DEFAULT_FROM_MAIL)
            send_mail(
                subject,
                email,
                sender,
                [user.email], fail_silently=False)

            messages.success(
                request,
                ('Thank you for registering in our site! Please check your '
                 'email to confirm your registration'))
            return HttpResponseRedirect(reverse('user_map:register'))
    else:
        form = UserForm()
    return render_to_response(
        'user_map/account/registration.html',
        {'form': form},
        context_instance=RequestContext(request)
    )


@login_forbidden
def confirm_registration(request, uid, key):
    """The view containing form to reset password and process it.

    :param request: A django request object.
    :type request: request

    :param uid: A unique id for a user.
    :type uid: str

    :param key: Key to confirm the user.
    :type key: str
    """
    decoded_uid = urlsafe_base64_decode(uid)
    try:
        user = User.objects.get(pk=decoded_uid)

        if not user.is_confirmed:
            if user.key == key:
                user.is_confirmed = True
                user.save(update_fields=['is_confirmed'])
                information = (
                    'Congratulations! Your account has been successfully '
                    'confirmed. Please continue to log in.')
            else:
                information = (
                    'Your link is not valid. Please make sure that you use '
                    'confirmation link we sent to your email.')
        else:
            information = ('Your account is already confirmed. Please '
                           'continue to log in.')
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        information = ('Your link is not valid. Please make sure that you use '
                       'confirmation link we sent to your email.')

    context = {
        'page_header_title': 'Registration Confirmation',
        'information': information
    }
    return render_to_response(
        'user_map/information.html',
        context,
        context_instance=RequestContext(request)
    )


@login_forbidden
def login(request):
    """Login view.

    :param request: A django request object.
    :type request: request
    """
    if request.method == 'POST':
        next_page = request.GET.get('next', '')
        if next_page == '':
            next_page = reverse('user_map:index')
        form = LoginForm(data=request.POST)
        if form.is_valid():
            user = authenticate(
                email=request.POST['email'],
                password=request.POST['password']
            )
            if user is not None:
                if user.is_active and user.is_confirmed:
                    django_login(request, user)

                    return HttpResponseRedirect(next_page)
                if not user.is_active:
                    errors = form._errors.setdefault(
                        NON_FIELD_ERRORS, ErrorList())
                    errors.append(
                        'The user is not active. Please contact our '
                        'administrator to resolve this.')
                if not user.is_confirmed:
                    errors = form._errors.setdefault(
                        NON_FIELD_ERRORS, ErrorList())
                    errors.append(
                        'Please confirm you registration email first!')
            else:
                errors = form._errors.setdefault(
                    NON_FIELD_ERRORS, ErrorList())
                errors.append(
                    'Please enter a correct email and password. '
                    'Note that both fields may be case-sensitive.')

    else:
        form = LoginForm()
    return render_to_response(
        'user_map/account/login.html',
        {'form': form},
        context_instance=RequestContext(request))


@login_required(login_url='user_map:login')
def update_user(request):
    """Update user view.

    :param request: A django request object.
    :type request: request
    """
    anchor_id = '#basic-information'
    if request.method == 'POST':
        if 'change_basic_info' in request.POST:
            anchor_id = '#basic-information'
            basic_info_form = BasicInformationForm(
                data=request.POST, instance=request.user)
            change_password_form = PasswordForm(user=request.user)
            if basic_info_form.is_valid():
                user = basic_info_form.save()
                messages.success(
                    request, 'You have succesfully changed your information!')
                return HttpResponseRedirect(
                    reverse('user_map:update_user') + anchor_id)
            else:
                anchor_id = '#basic-information'
        elif 'change_password' in request.POST:
            anchor_id = '#security'
            change_password_form = PasswordForm(
                data=request.POST, user=request.user)
            basic_info_form = BasicInformationForm(instance=request.user)
            if change_password_form.is_valid():
                user = change_password_form.save()
                messages.success(
                    request, 'You have successfully changed your password!')
                return HttpResponseRedirect(
                    reverse('user_map:update_user') + anchor_id)
            else:
                anchor_id = '#security'

    else:
        basic_info_form = BasicInformationForm(instance=request.user)
        change_password_form = PasswordForm(user=request.user)

    return render_to_response(
        'user_map/account/edit_user.html',
        {
            'basic_info_form': basic_info_form,
            'change_password_form': change_password_form,
            'anchor_id': anchor_id,
        },
        context_instance=RequestContext(request)
    )


@login_forbidden
def password_reset(request):
    """The view for reset password that contains a form to ask for email.

    :param request: A django request object.
    :type request: request
    """
    return django_password_reset(
        request,
        password_reset_form=CustomPasswordResetForm,
        template_name='user_map/account/password_reset_form.html',
        email_template_name='user_map/account/password_reset_email.html',
        post_reset_redirect=reverse('user_map:password_reset_done'))


@login_forbidden
def password_reset_done(request):
    """The view telling the user that an email has been sent.

    :param request: A django request object.
    :type request: request
    """
    return django_password_reset_done(
        request,
        template_name='user_map/account/password_reset_done.html')


@login_forbidden
def password_reset_confirm(request, uidb64=None, token=None):
    """The view containing form to reset password and process it.

    :param request: A django request object.
    :type request: request

    :param uidb64: An unique ID of the user.
    :type uidb64: str

    :param token: Token to check if the reset password link is valid.
    :type token: str
    """
    return django_password_reset_confirm(
        request,
        uidb64=uidb64,
        token=token,
        template_name='user_map/account/password_reset_confirm.html',
        set_password_form=CustomSetPasswordForm,
        post_reset_redirect=reverse('user_map:password_reset_complete'))


@login_forbidden
def password_reset_complete(request):
    """The view telling the user that reset password process has been completed.

    :param request: A django request object.
    :type request: request
    """
    return django_password_reset_complete(
        request,
        template_name='user_map/account/password_reset_complete.html')


def logout(request):
    """Log out view.

    :param request: A django request object.
    :type request: request
    """
    django_logout(request)
    return HttpResponseRedirect(reverse('user_map:index'))

