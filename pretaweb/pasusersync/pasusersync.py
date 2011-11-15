import logging

from Products.CMFCore.utils import getToolByName
from Products.Five import BrowserView
from Products.PluggableAuthService.interfaces.plugins import IUserAdderPlugin, IPropertiesPlugin, IUserFactoryPlugin
from Products.PlonePAS.sheet import MutablePropertySheet
from Products.Archetypes.config import REFERENCE_CATALOG
import transaction
from plone.i18n.normalizer.interfaces import IURLNormalizer
from zope.component import queryUtility

class PASUserSync(BrowserView):

    def __init__ (self, *args, **kwargs):
        BrowserView.__init__ (self, *args, **kwargs)
        self.portal = getToolByName(self.context, "portal_url")  .getPortalObject()


    def __call__ (self):

        request = self.request
        portal = getToolByName(self.context, "portal_url")  .getPortalObject()
        listPlugins = portal.acl_users.plugins.listPlugins


        # Get paramitors and corrispondign objects

        from_pluginid = request.get ("from")
        to_pluginid = request.get("to")

        # Allowing for more specific definition of the to property manager and
        # user manager
        if to_pluginid is None:
            to_properties_pluginid = request.get("to_properties")
            to_manager_pluginid = request.get("to_manager")
            to_userfactory_pluginid = request.get("to_userfactory")
        else:
            to_properties_pluginid = to_pluginid
            to_manager_pluginid = to_pluginid
            to_userfactory_pluginid = to_pluginid


        lowercase_normalize = request.get("lowercase_normalize",False)
        url_normalize = request.get("url_normalize",False)


        # Get plugin objects

        from_properties_plugin = None
        to_properties_plugin = None
        to_manager_plugin = None
        to_userfactory_plugin = None

        for pluginId, p in listPlugins(IPropertiesPlugin):
            if p.id == from_pluginid:
                from_properties_plugin = p
            elif pluginId == to_properties_pluginid:
                to_properties_plugin = p


        for pluginId, p in listPlugins(IUserAdderPlugin):
            if pluginId == to_manager_pluginid:
                to_manager_plugin = p
                break;
                
        for pluginId, p in listPlugins(IUserFactoryPlugin):
            if pluginId == to_userfactory_pluginid:
                to_userfactory_plugin = p
                break;
                


        # Check we have everything

        if not (to_manager_plugin and to_properties_plugin and to_userfactory_plugin and from_properties_plugin):
            raise Exception ("Cound not find needed plugin")


        # Do Sync

        return self.sync (from_properties_plugin, to_manager_plugin, to_properties_plugin, to_userfactory_plugin, lowercase_normalize, url_normalize)





    #
    # Syncing
    #

    def sync (self, from_properties, to_manager, to_properties, to_userfactory, lowercase_normalize=False, url_normalize=False):

        logging.info ("syncing...")

        allUserInfos =  self.portal.acl_users.searchUsers()
        loginSets = self.normalizedLoginSets (allUserInfos, lowercase_normalize, url_normalize)

        # Stats
        cadds = 0
        cremoves = 0
        cupdates = 0
        cnotupdates = 0
        saves = 0
        for loginSet in list(loginSets):


            # Get current User Objects from each of the plugins. A None return
            # means the plugin doesn't have data on that user
            userSet = self.userSetFromLogins (loginSet)
            fprop, fuser = self.getPropertiesForUser (from_properties, userSet)
            tprop, tuser = self.getPropertiesForUser (to_properties, userSet)


            # Operation on the user - update, add, remove, noop.
            # Operation is determined by which pluging returns valid
            # property sheets. 
            if fprop and tprop:
                # User is in both PAS plugins - do a sync
                result = self.sync_update (fprop, tprop, tuser, to_userfactory)

                if result:
                    logging.debug ("%s: updated.", tuser.getUserName())
                    cupdates += 1
                else:
                    logging.debug ("%s: up to date.", tuser.getUserName())
                    cnotupdates += 1


            elif fprop and (tprop is None):
                # User is not in the  target plugin - do an add then sync

                # Add
                self.sync_add (fuser.getUserName(), to_manager, fprop, to_properties, to_userfactory)

                # Sync - (re retreive relivant objects from the target
                # plugin)
                userSet = self.userSetFromLogins (loginSet)
                tprop, tuser = self.getPropertiesForUser (to_properties, userSet)
                self.sync_update (fprop, tprop, tuser, to_userfactory)

                logging.debug ("%s: added.", fuser.getUserName())
                cadds += 1


            elif (fprop is None) and tprop:
                loggin = tuser.getUserName() # get login to display on debug

                # User is nolonger in the source plugin - do a remove
                userId = tuser.getUserId()
                self.sync_remove (userId, to_manager)

                logging.debug ("%s: removed.", loggin)
                cremoves += 1


            else:

                # User does not exist in relivant plugins - do nothing
                
                logging.info ("(%s): user(s) does not exist in relivant plugins.", str(loginSet))
                cnotupdates += 1


                
            # Do a commit point every 20 database changes
            if (((cupdates + cremoves + cadds) / 20.0) - saves) > 1.0:
                transaction.commit()
                saves += 1
                logging.debug ("-- commit point --")


        results = "sync done (adds=%s updates=%s removes=%s not_updated=%s)" % (cadds, cupdates, cremoves, cnotupdates)

        logging.info (results)
        return results




    #
    # Sync Opertions
    #


    def sync_update (self, fprop, tprop, tuser ,to_userfactory):



        # Helper functions
        def pkeys (prop):
            if type(prop) == dict:
                return prop.keys()
            propMap = prop.propertyMap()
            return [p["id"] for p in propMap]

        def pget (prop, key):
            if type(prop) == dict:
                return prop.get(key)
            return prop.getProperty(key)



        updated_fields = []

        
        if isinstance (tprop, MutablePropertySheet):

            tpropMap = tprop.propertyMap()
            tkeys = set([p["id"] for p in tpropMap])

            # iterate from properties
            for key in pkeys(fprop):
                if key in tkeys:
                    fvalue = pget(fprop, key)
                    tvalue = tprop.getProperty(key)

                    # Test if tvalue is unicodable, otherwise set to None to
                    # re-set
                    try:
                        tvalue = tvalue.decode("utf8")
                    except UnicodeDecodeError:
                        tvalue = None
                                        
                    # compare value, is diff then update
                    # because there are different idears of Null. we don't want
                    # to override '' with None. 
                    #
                    # Test based on type first - because we want to be storing
                    # unicode strings.
                    if (fvalue or tvalue) and (fvalue != tvalue):
                        updated_fields.append(key)
                        tprop.setProperty (tuser, key, fvalue)    

                        
                        
        if len(updated_fields) > 0:

            if tprop.hasProperty("uid"):
                uid = tprop.getProperty("uid")
                referenceCatalog = getToolByName (self.portal, REFERENCE_CATALOG)
                usero = referenceCatalog.lookupObject (uid)
            else:
                ruser = to_userfactory.createUser (tuser.getId(), tuser.getName())
                if hasattr(ruser, "_getMembraneObject"):
                    usero = ruser._getMembraneObject()
                elif hasattr(user, "reindexObject"):
                    usero = ruser
                else:
                    usero = None
                
            if usero is not None:
                usero.reindexObject(updated_fields)
                
            return True

        else:
            return False
        
        

    def sync_add (self, login, to_manager, fprop, to_properties, to_userfactory):
        password = getToolByName(self.portal, 'portal_registration').generatePassword ()

        # do the deed
        to_manager.doAddUser (login, password)


    def sync_remove (self, login, to_manager):
        to_manager.doDeleteUser (login)





    #
    # Helper functions to retreive users and their properties
    #


    def getUser (self, login):
        try:
            user = self.portal.acl_users.getUser(login)
        except Exception, e:
            logging.error ("error in getting user '%s'", e)
            user = None
        return user
    

    def getPropertiesForUser (self, plugin, userSet):
        for user in userSet:
            try:
                prop = plugin.getPropertiesForUser(user)
            except:
                prop = None

            if type(prop) == dict and len(prop):
                return prop, user

            if prop and len(prop.propertyMap()):
                return prop, user
                
        return None, None


    def userSetFromLogins (self, logins):

        # produce a set of user objects from the logins

        userSet = set()

        doneLogins = set()
        for login in logins:
            user = self.getUser(login) # note: this may work better to iterrate thourgh the PAS plugins
            if user and user.getUserName() not in doneLogins:
                userSet.add(user)
            doneLogins.add(login)

        return userSet


    def normalizedLoginSets (self, userInfos, lowercase_normalize, url_normalize):

        normalize = queryUtility (IURLNormalizer).normalize

        logging.info ("Reading logins...")
        loginList = {}
        for userInfo in userInfos: 
            login = userInfo["login"]

            loginsNormalized = set([login])
            if lowercase_normalize:
                loginsNormalized.add (login.lower())

            if url_normalize:
                more = set()
                for l in loginsNormalized:
                    more.add(normalize(l))
                loginsNormalized = loginsNormalized | more

            loginSet = set(loginsNormalized)

            # add in sets allready in the loginList which are equivilent sets
            for l in loginsNormalized:
                lset = loginList.get(l)
                if lset:
                    loginSet.update(lset)

            # reset each indexed login to the same set
            for l in loginSet:
                loginList[l] = frozenset(loginSet)


        return set(loginList.values())

       


