import copy
import unittest
import style_matrix as matrix


class MatrixTest(unittest.TestCase):
    def fixture(self):
        operations=[];expansions=[];artifacts=[];files=[];ordinal=0
        for family,path,face in [('sans-serif','/system/fonts/Roboto.ttf',0),('sans-serif-condensed','/system/fonts/Roboto.ttf',0),('roboto','/system/fonts/Roboto.ttf',0),('','/system/fonts/Cjk.ttc',2)]:
            expansions.append({'ordinal':ordinal,'preserveItalic':bool(family)})
            for weight in (100,200,300,400,450,500,520,600,700,800,900):
                aid=family+str(weight)
                operations.append({'targetPath':path,'node':{'index':face,'weight':400,'family':family,'ordinal':ordinal},'expandedWeight':weight,'artifact':{'artifactId':aid}})
                artifacts.append({'artifactId':aid,'staticXmlContract':{'faceIndex':0}})
                files.append({'logicalPath':'/system/fonts/LuoShuFixed-'+aid+'.ttf','sha256':'new-'+aid,'kind':'xml-static-font','artifactIds':[aid]})
            ordinal+=1
        files.append({'logicalPath':'/system/fonts/LuoShu-Original-Roboto.ttf','sha256':'Roboto','kind':'xml-original'})
        observed=[]
        for case in matrix.cases():
            name='Cjk.ttc' if case['sample']=='中' else 'Emoji.ttf' if case['sample']=='😀' else 'Roboto.ttf'
            item=copy.deepcopy(case);item['raster']='original-raster-'+str(case)
            item['actualFonts']=[{'file':'/system/fonts/'+name,'face':2 if name=='Cjk.ttc' else 0,
                                  'weight':case['weight'],'slant':int(case['italic']), 'sha256':name.split('.')[0]}]
            observed.append(item)
        route={'routeRevision':2,'documents':{'/system/etc/font_fallback.xml':{'operations':operations,'styleExpansions':expansions}}}
        return route,{'artifacts':artifacts},{'files':files},{'cases':observed}

    def test_all_styles_use_new_static_or_explicit_original(self):
        result=matrix.expected_cases(*self.fixture())
        self.assertEqual(len(result),54)
        for case in result:
            e=case['expected']
            if case['sample'] in ('Ω','😀') or (case['italic'] and case['sample'] in ('A','1')):
                self.assertIn('raster',e)
                if case['sample']!='😀':self.assertIn('LuoShu-Original-',e['path'])
            else:
                self.assertIn('LuoShuFixed-',e['path']);self.assertEqual(e['fontWeight'],case['weight'])
                self.assertEqual(e['fontSlant'],0);self.assertEqual(e['face'],0)

    def test_legacy_result_cannot_count_as_new_style_proof(self):
        values=self.fixture();values[1]['artifacts'][0].pop('staticXmlContract')
        with self.assertRaisesRegex(ValueError,'legacy'):matrix.expected_cases(*values)

    def test_duplicate_or_missing_case_refused(self):
        for duplicate in (False,True):
            values=self.fixture();values[3]['cases'].pop()
            if duplicate:values[3]['cases'].append(values[3]['cases'][0])
            with self.assertRaisesRegex(ValueError,'baseline'):matrix.expected_cases(*values)

    def test_unsealed_original_refused(self):
        values=self.fixture();values[2]['files'].pop()
        with self.assertRaisesRegex(ValueError,'sealed'):matrix.expected_cases(*values)

    def test_wrong_original_face_cannot_pick_another_route(self):
        values=self.fixture();values[3]['cases'][0]['actualFonts'][0]['face']=1
        with self.assertRaisesRegex(ValueError,'unique'):matrix.expected_cases(*values)


if __name__=='__main__':unittest.main()
