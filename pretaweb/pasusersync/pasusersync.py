from zope.interface import implements, Interface
from zope.component import getMultiAdapter

from Products.Five import BrowserView
from Products.CMFCore.utils import getToolByName
from Products.PluggableAuthService.PluggableAuthService import logger
from Products.PluggableAuthService.utils import classImplements
from Products.PluggableAuthService.plugins.BasePlugin import BasePlugin
from Products.PlonePAS.interfaces.plugins import IUserIntrospection
from interfaces import IPASUserAdder, IPASUserDisabler, IPASUserSync
import OFS.Cache

try:
    from Products.PluggableAuthService import _SWALLOWABLE_PLUGIN_EXCEPTIONS
except ImportError:  # in case that private const goes away someday
    _SWALLOWABLE_PLUGIN_EXCEPTIONS = NameError, AttributeError, KeyError, TypeError, ValueError


#class PASUserSyncView(BrowserView): 


class PASUserSync(object):
    """
    BelronUserProps browser view
    """
    implements(IPASUserSync)

    def __init__(self, from_ctx, to_ctx):
        self.from_ctx = from_ctx
        self.to_ctx = to_ctx

    def pas_diff(self):
        """ Plan is to enumberate all users and then compare them and see which plugin they come from
            For any that aren't in all plugins, do add or remove
        """
        #lister = IUserEnumerationPlugin

        if isinstance(self.from_ctx, OFS.Cache.Cacheable):
            self.from_ctx.ZCacheable_invalidate ()
        if isinstance(self.to_ctx, OFS.Cache.Cacheable):
            self.to_ctx.ZCacheable_invalidate ()


        from_logins = [u["login"] for u in self.from_ctx.enumerateUsers()]
        from_logins = set(from_logins)

        to_logins = [u["login"] for u in self.to_ctx.enumerateUsers()]
        to_logins = set(to_logins)

        adds = from_logins - to_logins
        removes = to_logins - from_logins

        return list(adds), list(removes)



    @property
    def portal(self):
        return getToolByName(self.context, 'portal_url').getPortalObject()


    def listAllPASUsers(self):
        """
        List all user's in AD
        """
       #self.luf = self.context.acl_users.ad.acl_users #PASUserFolder instance
        return self.luf.searchUsers(cn='',objectClass='top;person;organizationalPerson;user')


    def synchronisePASUsers(self):
        """
        Synchronise the Plone users with the PAS server
        """
        usersAdded = []
        usersSynced = {}
        usersDisabled = []
        existingUsers = []
        #for user in self.context.users.objectIds('BelronUser'):
        #    existingUsers.append(user)
        #self.context.plone_log(existingUsers)
        for pasuser in self.listAllPASUsers():
            login = pasuser.get('sAMAccountName')
            if login is not None:
                # This is what PAS expects teh login to be
                login = 'obrien\\'+login.lower() # the way IIS formats the login
                user = self.context.acl_users.getUser(login)
                if user is None:  # user doesn't exist
                    user = self.makeMember(login)
                    #now get plones concept of the userId
                    userId = user.getId()
                    #membershipTool.setLoginTimes()  # Doesn't work, because it explicitly checks to see if membershipTool.isAnonymousUser() and bails out since we are, at this point, anonymous (because apachepas (or whatever IAuthenticationPlugin you're using) hasn't done its thing yet).
                    self.setLoginTimes(userId, membershipTool)  # lets the user show up in member searches. We do this only when we first create the member. This means the login times are less accurate than in a stock Plone with form-based login, in which the times are set at each login. However, if we were to set login times at each request, that's an expensive DB write at each, and lots of ConflictErrors happen.
                    # Do the stuff normally done in the logged_in page (for some silly reason). Unfortunately, we'll be doing this for each authenticated request rather than just at login. Optimize if necessary:
                    membershipTool.createMemberArea(member_id=userId)
                    usersAdded.append(login)
                else:
                    #now get plones concept of the userId
                    userId = user.getId()
                    usersSynced[login] = self.syncProps(userId, pasuser)

                # Remove userid that exists in AD as well as in Plone
                #if userId in existingUsers:
                #    existingUsers.remove(userId)
                # Disable the users that have been disabled in AD
                #if str(pasuser.get('userAccountControl')) == '514':
                #    if self.handleDisable(userId, True):
                #        usersDisabled.append(login)
                # Disable the users that no longer exist in AD
                #for userId in existingUsers:
                #    if self.handleDisable(userId, True):
                #        usersDisabled.append(userId)
 
        return {'usersAdded': usersAdded, 'usersSynced': usersSynced, 'usersDisabled': usersDisabled}



class PASUserSyncView(BrowserView):

    def __call__(self, *args, **kwargs):
        from_plugin = 'ldap'
        to_plugin = 'membrane_users'

        from_ctx = getattr (self.context.acl_users, from_plugin)
        to_ctx = getattr (self.context.acl_users, to_plugin)


        if not (from_ctx and to_ctx):
            raise Exception ("PAS-Sync plugin configuration error")


        syncer = getMultiAdapter ((from_ctx, to_ctx),IPASUserSync)

        adds, removes = syncer.pas_diff ()
        adder = getMultiAdapter ((from_ctx, to_ctx),IPASUserAdder)
        remover = getMultiAdapter ((from_ctx, to_ctx),IPASUserDisabler)
        for user in adds:
            adder.add_user(user)
        for user in removes:
            remover.disable_user(user)
        return "adds=%s, removes=%s" % (adds,removes)


