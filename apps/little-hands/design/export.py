#!/usr/bin/env python3
"""Export existing staging GET responses for visual source. Never acceptance proof."""
import argparse
import hashlib
import json
import os
import sys
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parent
APP=ROOT.parent


class Sanitizer(HTMLParser):
    allowed={'id','class','lang','dir','title','role','alt','width','height','src','href','rel','name','type','placeholder','for','tabindex','rows','cols','min','max','step','required','disabled','checked','selected','multiple','scope','colspan','rowspan','viewbox','preserveaspectratio','x','y','rx','ry','cx','cy','r','d','fill'}
    voids={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.output=[]
        self.suppressed=[]

    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        blocked=tag in {'script','style','template','noscript','meta','base'} or 'hidden' in attrs or tag=='input' and attrs.get('type')=='hidden'
        if blocked or self.suppressed:
            if tag not in self.voids:self.suppressed.append(tag)
            return
        if tag=='input' and attrs.get('type')=='password':
            attrs={key:value for key,value in attrs.items() if key in {'id','class','name','type','placeholder','required','autocomplete'}}
        selected={key:value for key,value in attrs.items() if key in self.allowed or key.startswith('aria-') or key in {'data-native-key','data-native-type','data-action','data-app','data-environment'}}
        if tag=='form':
            selected.update({'inert':None,'data-export-only':'true','method':attrs.get('method','get')})
        if tag=='button':selected['type']='button'
        self.output.append('<'+tag+''.join(' '+key+('="'+escape(value,quote=True)+'"' if value is not None else '') for key,value in selected.items())+'>')

    def handle_endtag(self,tag):
        if self.suppressed:
            if tag==self.suppressed[-1]:self.suppressed.pop()
            return
        self.output.append('</'+tag+'>')

    def handle_data(self,data):
        if not self.suppressed:self.output.append(data)

    def handle_entityref(self,name):
        if not self.suppressed:self.output.append('&'+name+';')

    def handle_charref(self,name):
        if not self.suppressed:self.output.append('&#'+name+';')


def sanitize(source):
    parser=Sanitizer();parser.feed(source)
    return '<!doctype html>\n'+''.join(parser.output)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if os.environ.get('LH_ENV')!='staging':
        parser.error('Only explicitly configured staging is allowed.')
    sys.path.insert(0,str(APP));os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
    import django
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.test import Client
    from booking.models import Booking,ClassSession
    from django.utils import timezone
    if settings.ENVIRONMENT!='staging':parser.error('Django settings must be staging.')
    User=get_user_model()
    member=User.objects.get(username='member-a',is_superuser=False,is_staff=False)
    operator=User.objects.get(username='operator',is_superuser=False)
    if not operator.has_perm('booking.manage_operations'):parser.error('Existing operator lacks operations permission.')
    routes=[('publichome','public','/'),('login','public','/accounts/login/'),('signup','public','/accounts/signup/'),('memberhome','member','/'),('mybookings','member','/bookings/'),('notifications','member','/notifications/'),('staffdashboard','operator','/staff/'),('staffsessions','operator','/staff/sessions/'),('staffcreate','operator','/staff/sessions/new/'),('staffaudit','operator','/staff/audit/'),('403','member','/staff/'),('404','public','/not-a-real-route/')]
    pending=['review requires actual POST response','conflict requires actual409 response']
    session=ClassSession.objects.filter(status='scheduled',course__active=True,starts_at__gt=timezone.now()).order_by('starts_at','pk').first()
    if session:
        routes += [('sessionavailable','member',f'/sessions/{session.pk}/'),('staffroster','operator',f'/staff/sessions/{session.pk}/'),('staffedit','operator',f'/staff/sessions/{session.pk}/edit/')]
    else:pending.append('No existing future scheduled session')
    for status,state in [('confirmed','confirmed'),('waitlisted','waitlisted'),('cancelled','cancelled')]:
        booking=Booking.objects.filter(member=member,status=status).order_by('-pk').first()
        if booking:
            routes.append((state,'member',f'/bookings/{booking.public_id}/'))
            if status=='confirmed':routes += [('cancelconfirm','member',f'/bookings/{booking.public_id}/cancel/'),('reschedule','member',f'/bookings/{booking.public_id}/reschedule/')]
        else:pending.append('No existing member-a '+status+' booking')
    args.out.mkdir(parents=True,exist_ok=False)
    site=urlsplit(settings.SITE_URL)
    clients={key:Client(SERVER_NAME=site.hostname,SERVER_PORT=str(site.port or 443 if site.scheme=='https' else site.port or 80)) for key in ('public','member','operator')}
    clients['member'].force_login(member,backend='django.contrib.auth.backends.ModelBackend')
    clients['operator'].force_login(operator,backend='django.contrib.auth.backends.ModelBackend')
    exports=[]
    for state,role,route in routes:
        response=clients[role].get(route,secure=site.scheme=='https',HTTP_HOST=site.netloc)
        if response.status_code not in {200,403,404}:
            pending.append(state+': unexpected GET status '+str(response.status_code));continue
        content=sanitize(response.content.decode('utf-8'))
        path=args.out/(state+'.html');path.write_text(content)
        exports.append({'state':'state-'+state,'role':role,'route':route,'method':'GET','status':response.status_code,'path':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    result={'schema':'little-hands-staging-ssr-export-v1','scope':'Visual source GET export with existing staging accounts. force_login only prepares visual session; this is not authentication, business-action, browser, or acceptance proof.','exports':exports,'pending':pending}
    (args.out/'exports.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'exported':len(exports),'pending':pending,'proof':'visual SSR only'},ensure_ascii=False))


if __name__=='__main__':main()
