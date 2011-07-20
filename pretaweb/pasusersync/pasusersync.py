from zope.interface import implements, Interface

from Products.Five import BrowserView
from Products.CMFCore.utils import getToolByName
from Products.PluggableAuthService.PluggableAuthService import logger
from Products.PluggableAuthService.interfaces.plugins import IAuthenticationPlugin, IUserAdderPlugin, IRoleAssignerPlugin
from Products.PluggableAuthService.utils import classImplements
from Products.PluggableAuthService.plugins.BasePlugin import BasePlugin
from Products.PlonePAS.interfaces.plugins import IUserIntrospection
from interfaces import IPASUserSync, IUserAdder, IUserDisabler

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

    def __init__(self, context):
        self.context = context

    def sync_pas(self, from_plugin, to_plugin):
        """ Plan is to enumberate all users and then compare them and see which plugin they come from
            For any that aren't in all plugins, do add or remove
        """
        #lister = IUserEnumerationPlugin
        user_list = self.context.acl_users.searchUsers() #this could be bad for performance
        user_map = {}
        for user in user_list:
            login = user['login']
            id= user['id']
            pluginid = user['pluginid']
            user_map.setdefault(login,{})[pluginid] = user
        adds = []
        removes = []
        for login,plugins in user_map.items():
            if from_plugin in plugins and to_plugin not in plugins:
                adds.append(plugins[from_plugin]['login'])
            elif from_plugin not in plugins and to_plugin in plugins:
                removes.append(plugins[to_plugin]['login'])
        return (adds,removes)




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




class PASUserAdder(object):
    implements(IUserAdder)

    def __init__(self, context):
        self.context = context

    def add_user(self, login, pluginid=None):
        """Make a user with id `userId`, and assign him the Member role."""

        # I could just call self.context.acl_users._doAddUser(...), but that's private and not part of the IPluggableAuthService interface. It might break someday. So the following is based on PluggableAuthService._doAddUser():
            
        # Make sure we actually have user adders and role assigners. It would be ugly to succeed at making the user but be unable to assign him the role.
        userAdders = self.context.acl_users.plugins.listPlugins(IUserAdderPlugin)
        if not userAdders:
            raise NotImplementedError("I wanted to make a new user, but there are no PAS plugins active that can make users.")
        roleAssigners = self.context.acl_users.plugins.listPlugins(IRoleAssignerPlugin)
        if not roleAssigners:
            raise NotImplementedError("I wanted to make a new user and give him the Member role, but there are no PAS plugins active that assign roles to users.")
        
        # Add the user to the first IUserAdderPlugin that works:
        generatePassword = getToolByName(self.context, 'portal_registration').generatePassword
        user = None
        for adder_id, curAdder in userAdders:
            if pluginid is not None and adder_id != pluginid:
                continue
            if curAdder.doAddUser(login, generatePassword()):  # Assign a dummy password. It'll never be used if you're using apachepas to delegate authentication to Apache.
                user = self.context.acl_users.getUser(login)
                break
            
        # Map the Member role to the user using all available IRoleAssignerPlugins (just like doAddUser does for some reason):
        for curAssignerId, curAssigner in roleAssigners:
            try:
                curAssigner.doAssignRoleToPrincipal(user.getId(), 'Member')
            except _SWALLOWABLE_PLUGIN_EXCEPTIONS:
                logger.debug('RoleAssigner %s error' % curAssignerId, exc_info=True)

        #now get plones concept of the userId
        userId = user.getId()
        #membershipTool.setLoginTimes()  # Doesn't work, because it explicitly checks to see if membershipTool.isAnonymousUser() and bails out since we are, at this point, anonymous (because apachepas (or whatever IAuthenticationPlugin you're using) hasn't done its thing yet).
        self.setLoginTimes(userId)  # lets the user show up in member searches. We do this only when we first create the member. This means the login times are less accurate than in a stock Plone with form-based login, in which the times are set at each login. However, if we were to set login times at each request, that's an expensive DB write at each, and lots of ConflictErrors happen.
        # Do the stuff normally done in the logged_in page (for some silly reason). Unfortunately, we'll be doing this for each authenticated request rather than just at login. Optimize if necessary:
        membershipTool = getToolByName(self.context, 'portal_membership')
        membershipTool.createMemberArea(member_id=userId)

        return user


    def setLoginTimes(self, userId):
        """Do what the logged_in script usually does, with regard to login times, to users after they log in."""
        # Ripped off and simplified from CMFPlone.MembershipTool.MembershipTool.setLoginTimes():
        membershipTool = getToolByName(self.context, 'portal_membership')
        member = membershipTool.getMemberById(userId)
        now = self.context.ZopeTime()
        defaultDate = '2000/01/01'
            
        # Duplicate mysterious logic from MembershipTool.py:
        lastLoginTime = member.getProperty('login_time', defaultDate)  # In Plone 2.5, 'login_time' property is DateTime('2000/01/01') when a user has never logged in, so this default never kicks in. However, I'll assume it was in the MembershipTool code for a reason.
        if str(lastLoginTime) == defaultDate:
            lastLoginTime = now
        member.setMemberProperties({'login_time': now, 'last_login_time': lastLoginTime})


    def syncProps(self, userId, pasuser):
        """Sync Plone user attributes"""
        membershipTool = getToolByName(self.context, 'portal_membership')
        membraneTool = getToolByName(self.context, 'membrane_tool')
        member = membershipTool.getMemberById(userId)
        newprops = {}
        for attrib,field in config.AttributeMappings.items():
            if pasuser.get(attrib):
                newprops[field] = pasuser.get(attrib)
        addParts = ['streetAddress','l','st','postalCode','postOfficeBox']
        officeAddress = [pasuser.get(f) for f in addParts if pasuser.get(f)]
        if officeAddress:
            officeAddress = ', '.join(officeAddress)
            newprops['officeAddress'] = officeAddress

        #remove properties that haven't changed
        newprops = dict([(k,v) for k,v in newprops.items() if member.getProperty(k)!=v])

        if newprops:
            member.setMemberProperties(newprops)
            membraneTool.reindexObject(membraneTool)
        return newprops


class MembraneDisabler(object):
    implements(IUserDisabler)

    def __init__(self, context):
        self.context = context

    def disable_user(self, userid):
        """Disable applicable users"""
        self.context.plone_log(userId)
        if always_disable:
            ob = getattr(self.context.users, userId)
            rs = self.context.portal_workflow.getInfoFor(ob, 'review_state')
            if rs != 'disabled':
                self.context.portal_workflow.doActionFor(ob, 'disable')
                return True
        return False



class PASUserSyncView(BrowserView):

    def __call__(self, *args, **kwargs):
        from_plugin = 'ldap'
        to_plugin = 'membrane_users'


        syncer = IPASUserSync(self.context)
        adds, removes = syncer.sync_pas(from_plugin, to_plugin)
        adder = IUserAdder(self.context)
        remover = IUserDisabler(self.context)
        for user in adds:
            adder.add_user(user, to_plugin)
        for user in removes:
            remover.disable_user(user, from_plugin)
        return "adds=%s, removes=%s" % (adds,removes)
